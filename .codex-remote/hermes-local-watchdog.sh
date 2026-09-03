#!/usr/bin/env bash
set -euo pipefail

LOG=/home/yi/hermes-local-watchdog.log
# Pick the currently active engine. If none is healthy, recover the configured
# default AWQ engine instead of reviving a previously used model mid-switch.
MODEL_SERVICE=$(systemctl --user is-active --quiet huihui-qwen36-awq-vllm.service \
  && echo huihui-qwen36-awq-vllm.service \
  || { systemctl --user is-active --quiet ornith-a3b-vllm.service \
    && echo ornith-a3b-vllm.service \
    || { systemctl --user is-active --quiet qwen38-27b-uncensored-fp8-vllm.service \
      && echo qwen38-27b-uncensored-fp8-vllm.service \
      || echo huihui-qwen36-awq-vllm.service; }; })
ROUTER_SERVICE=vllm-think-router.service
MODEL_URL=http://127.0.0.1:8001/v1/models
ROUTER_HEALTH=http://127.0.0.1:8080/health
GATEWAY_SERVICE=hermes-gateway.service
GATEWAY_CLOSE_WAIT_LIMIT=400  # [2026-08-19] was 60. fd soft limit is 1024, so close_wait=72 was NEVER dangerous;
                              # killing the gateway at 72 interrupted the user's running task. Active-use peak observed: 73.
GATEWAY_FD_LIMIT=700          # [2026-08-19] was 300; real ceiling is the 1024 fd soft limit

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$LOG"; }


# 切换进行中就整轮跳过。切换有个窗口:旧引擎已被 Conflicts 停掉,新引擎还在
# ExecStartPre 等显存排空,此刻两个都不 active。没有这道闸,看门狗会判定
# "引擎挂了"并重启它上次认识的那个,而那个的 Conflicts 又会把正在起的新引擎
# SIGTERM 掉 —— 2026-08-27 11:21:24 就是这么把 qwen 杀掉的。
if [ -f /tmp/vllm-engine-switch.lock ]; then
  log "skip: engine switch in progress"
  exit 0
fi

restart_user_service() {
  local svc=$1
  log "restart $svc"
  systemctl --user restart "$svc" || log "restart_failed $svc"
}

wait_http() {
  local url=$1
  local seconds=${2:-90}
  local deadline=$((SECONDS + seconds))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  return 1
}

# Backend model must expose /v1/models. This is safe and does not interrupt user turns.
if ! curl -fsS --max-time 8 "$MODEL_URL" >/dev/null 2>&1; then
  log "model_backend_unhealthy url=$MODEL_URL"
  restart_user_service "$MODEL_SERVICE"
  if wait_http "$MODEL_URL" 600; then
    log "model_backend_recovered"
  else
    log "model_backend_still_down"
    exit 1
  fi
fi

# Router health endpoint only. Do not send chat smoke tests: those can collide with max-num-seqs=1.
if ! curl -fsS --max-time 8 "$ROUTER_HEALTH" | grep -q '"ok":true'; then
  log "router_unhealthy url=$ROUTER_HEALTH"
  restart_user_service "$ROUTER_SERVICE"
  if wait_http "$ROUTER_HEALTH" 30; then
    log "router_recovered"
  else
    log "router_still_down"
    exit 1
  fi
fi

log "ok"

# Telegram/proxy transport guard. A local model can answer while Telegram delivery is wedged
# if httpx sockets pile up in CLOSE-WAIT behind Clash; restarting only the gateway clears it.
GATEWAY_PID=$(systemctl --user show -p MainPID --value "$GATEWAY_SERVICE" 2>/dev/null || true)
if [[ -n "${GATEWAY_PID:-}" && "$GATEWAY_PID" != "0" && -d "/proc/$GATEWAY_PID" ]]; then
  FD_COUNT=$(ls "/proc/$GATEWAY_PID/fd" 2>/dev/null | wc -l || printf "0")
  CLOSE_WAIT_COUNT=$(ss -tanp 2>/dev/null | grep "pid=$GATEWAY_PID," | grep -c "CLOSE-WAIT" || true)
  if (( FD_COUNT > GATEWAY_FD_LIMIT || CLOSE_WAIT_COUNT > GATEWAY_CLOSE_WAIT_LIMIT )); then
    log "gateway_transport_wedged pid=$GATEWAY_PID fd=$FD_COUNT close_wait=$CLOSE_WAIT_COUNT"
    restart_user_service "$GATEWAY_SERVICE"
    log "gateway_restarted_after_transport_wedge"
  fi
else
  log "gateway_not_running"
  restart_user_service "$GATEWAY_SERVICE"
fi

# [2026-08-19] Real failure signal, not a proxy-socket guess: if the Telegram adapter
# cannot connect, the gateway is silently deaf (it stays "active" but receives nothing --
# exactly what happened at 12:0x when NO_PROXY sent it to a DNS-poisoned address).
# Restarting on THIS is worth it; restarting on CLOSE-WAIT alone was not.
TELEGRAM_FAIL_LIMIT=3
# [2026-08-23] Widened: only matching "Failed to connect to Telegram" missed a
# real outage. When clash blips, the adapter logs "Telegram network error" and
# "Telegram polling degraded (heartbeat probe)" instead, retries internally, and
# can stay wedged after the network recovers -- the gateway looks active while
# silently receiving nothing. Count all three signals.
TG_FAILS=$(journalctl --user -u "$GATEWAY_SERVICE" --since "3 minutes ago" --no-pager 2>/dev/null            | grep -cE "Failed to connect to Telegram|Telegram network error|Telegram polling degraded" || true)
if (( TG_FAILS >= TELEGRAM_FAIL_LIMIT )); then
  log "telegram_unreachable fails=$TG_FAILS in 3min -> restarting gateway"
  restart_user_service "$GATEWAY_SERVICE"
  log "gateway_restarted_after_telegram_failure"
fi
