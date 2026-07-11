-- msgptr_trace.lua : 메시지 포인터 슬롯 테이블 $7E:C58B 기록을 후킹.
--   핸들러가 `LDA $0000,Y / STA $7EC58B,X`로 텍스트 포인터를 슬롯에 저장한다.
--   기록 순간의 PC·값·X·Y·DBR을 잡으면, 값=$89FF(레이스 대사 포인터)를 실은
--   상위 명령 스트림의 ROM 위치(=DBR:Y)를 역추적할 수 있다.
-- 산출: tmp/trace/msgptr_trace.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local LO, HI = 0xC000, 0xCFFF     -- 속성 배열 전체 감시(WRAM 선형 오프셋)
local STOP_FRAME = 1095
local log = {}

-- 정확히 대사 텍스트 포인터 $89FF가 슬롯에 기록되는 순간만 포착 + 호출자 복귀주소.
local TARGET = 0x89FF
local function onWrite(addr, value)
  if #log > 60 then return end
  local st = emu.getState()
  local a = st["cpu.a"]
  if a ~= TARGET then return end
  local s = st["cpu.sp"]
  -- 최근 JSL/JSR 복귀주소 후보(스택 상위 몇 워드) — 호출자 규명용
  local st1 = emu.read(s + 1, emu.memType.snesMemory) | (emu.read(s + 2, emu.memType.snesMemory) << 8) | (emu.read(s + 3, emu.memType.snesMemory) << 16)
  log[#log + 1] = string.format(
    "f=%-5d PC=$%02X:%04X addr=$%06X A=%04X X=%04X Y=%04X DBR=%02X ret?=$%06X",
    st["frameCount"], st["cpu.k"], st["cpu.pc"], addr, a, st["cpu.x"], st["cpu.y"], st["cpu.dbr"], st1)
end

emu.addMemoryCallback(onWrite, emu.callbackType.write, LO, HI, emu.cpuType.snes, emu.memType.snesWorkRam)

local function pressStart(on)
  local ok = pcall(function() emu.setInput(1, { start = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { start = on }) end) end
end

local done = false
local function onFrame()
  local fr = emu.getState()["frameCount"]
  local on = (fr >= 200 and fr < 208) or (fr >= 400 and fr < 408) or (fr >= 600 and fr < 608)
  pressStart(on)
  if fr >= STOP_FRAME and not done then
    done = true
    local f = io.open(ROOT .. "msgptr_trace.txt", "w")
    f:write(string.format("watch $7E:%04X-%04X writes, up to f%d, count=%d\n\n", LO, HI, STOP_FRAME, #log))
    for _, s in ipairs(log) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end
emu.addEventCallback(onFrame, emu.eventType.endFrame)
