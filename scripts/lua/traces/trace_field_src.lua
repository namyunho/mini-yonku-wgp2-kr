-- trace_field_src.lua : System ① 텍스트 갭(맵/필드 NPC·포메이션 레츠 대사) 소스/디코더 규명.
--   맵/NPC 대화가 "깨진 한글"로 렌더 = $CA 압축글리프 시트 경유 = System ① 디코더 확정.
--   후보 2택을 동시에 시간순 후킹해, 대사가 뜨는 순간 어느 경로가 증가하는지 특정한다:
--     (P) 파서 $C1:9554        — 673 정적 대사 엔진. 진입 시 소스 글리프주소 DBR:Y + 호출처.
--     (S) 씬표 읽기 $C6:9C57   — 어드벤처 씬VM 로드. 읽은 오프셋 → 씬 id.
--     (D) 디코더 진입 $C0:39D5 — 어드벤처 압축소스 디컴프. DP $0A/$0B/$0C = 소스(bank:addr).
--
--   사용법(맥):
--     1) Mesen 으로 out/wgp2_kr.smc 로드(세이브 스테이트 사용 시 파일명 반드시 wgp2_kr.smc).
--     2) 이 스크립트 실행 → 화면 우상단에 P/S/D 카운터가 뜬다.
--     3) 포메이션 설정 화면으로 이동 → 레츠(또는 NPC) 대사가 뜨는 순간
--        어느 카운터가 증가하는지 관찰(P=파서 / S·D=어드벤처).
--     4) tmp/trace/field_src_log.txt 에 시간순 이벤트(소스주소 포함) 기록됨.
--   ScriptWindow.AllowIoOsAccess=true 필요.
local OUT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/field_src_log.txt"
local SCENE_TBL = 0xC69C57

local log = {}          -- 이벤트 라인 링버퍼(최근 N)
local MAXLOG = 400
local nP, nS, nD = 0, 0, 0
local lastParserSrc = -1
local lastScene = -1

local function push(line)
  local fc = emu.getState()["frameCount"] or 0
  log[#log + 1] = string.format("f=%-8d %s", fc, line)
  if #log > MAXLOG then table.remove(log, 1) end
end

local function flush()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write(string.format("# field-src trace  P(parser)=%d  S(scene)=%d  D(decode)=%d\n", nP, nS, nD))
  f:write("# P=파서$C1:9554(673)  S=씬표$C6:9C57(어드벤처)  D=디코더$C0:39D5(어드벤처)\n\n")
  for _, l in ipairs(log) do f:write(l .. "\n") end
  f:close()
end

-- (P) 파서 진입: 소스 글리프주소 DBR:Y + 호출처(JSL 복귀주소)
emu.addMemoryCallback(function()
  local st = emu.getState()
  local dbr, y, s = st["cpu.dbr"], st["cpu.y"], st["cpu.sp"]
  if dbr == nil or y == nil then return end
  local src = dbr * 0x10000 + y
  if src == lastParserSrc then return end     -- 같은 문자열 연속 진입 억제
  lastParserSrc = src
  nP = nP + 1
  local ret = 0
  if s ~= nil then
    ret = (emu.read(s + 3, emu.memType.snesMemory) << 16)
        | (emu.read(s + 2, emu.memType.snesMemory) << 8)
        |  emu.read(s + 1, emu.memType.snesMemory)
  end
  push(string.format("P parser  src=%02X:%04X  caller=$%06X", dbr, y, ret))
  flush()
end, emu.callbackType.exec, 0xC19554, 0xC19554, emu.cpuType.snes, emu.memType.snesMemory)

-- (S) 씬표 읽기: 로드되는 씬 id
emu.addMemoryCallback(function(addr, value)
  local sid = (addr - SCENE_TBL) // 3
  if sid < 0 or sid >= 250 then return end
  if sid == lastScene then return end
  lastScene = sid
  nS = nS + 1
  push(string.format("S scene   id=0x%02X", sid))
  flush()
end, emu.callbackType.read, SCENE_TBL, SCENE_TBL + 250 * 3 - 1, emu.cpuType.snes, emu.memType.snesMemory)

-- (D) 디코더 진입: DP $0A/$0B/$0C = 압축소스(bank:addr)
emu.addMemoryCallback(function()
  local d = emu.getState()["cpu.d"] or 0
  local lo = emu.read(d + 0x0A, emu.memType.snesMemory)
  local hi = emu.read(d + 0x0B, emu.memType.snesMemory)
  local bk = emu.read(d + 0x0C, emu.memType.snesMemory)
  nD = nD + 1
  push(string.format("D decode  src=%02X:%02X%02X", bk, hi, lo))
  flush()
end, emu.callbackType.exec, 0xC039D5, 0xC039D5, emu.cpuType.snes, emu.memType.snesMemory)

-- 화면 카운터(실기에서 어느 경로가 증가하는지 육안 확인)
local fc = 0
emu.addEventCallback(function()
  fc = fc + 1
  if fc % 30 == 0 then
    emu.displayMessage("field-src", string.format("P=%d S=%d D=%d", nP, nS, nD))
    pcall(flush)
  end
end, emu.eventType.endFrame)

emu.displayMessage("field-src", "armed: P=parser S=scene D=decode")
