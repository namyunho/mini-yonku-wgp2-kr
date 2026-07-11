-- parser_caller.lua : 대사 파서 $C1:9554 진입을 후킹해 호출자·베이스 포인터를 포착.
--   JSL 복귀주소(스택 S+1..S+3) = 호출자 위치. Y/DBR/$7EA5E0 = 스크립트 베이스·카운터.
--   레이스 대사 시작(frame~1080) 전후의 첫 호출들을 기록 → 포인터 테이블 진입점 규명.
-- 산출: tmp/trace/parser_caller.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local STOP_FRAME = 1120
local log = {}

local function onExec()
  local st = emu.getState()
  local fr = st["frameCount"]
  if fr < 1080 then return end
  if #log > 40 then return end
  local s = st["cpu.sp"]
  -- JSL 복귀: S+1(lo) S+2(hi) S+3(bank). read via CPU 버스
  local r1 = emu.read(s + 1, emu.memType.snesMemory)
  local r2 = emu.read(s + 2, emu.memType.snesMemory)
  local r3 = emu.read(s + 3, emu.memType.snesMemory)
  local ret = (r3 << 16) | (r2 << 8) | r1   -- 복귀주소(=JSL 다음-1)
  local counter = emu.read(0x7EA5E0, emu.memType.snesMemory) | (emu.read(0x7EA5E1, emu.memType.snesMemory) << 8)
  log[#log + 1] = string.format("f=%-5d ret=$%06X Y=%04X DBR=%02X cnt($7EA5E0)=%04X SP=%04X",
    fr, ret, st["cpu.y"], st["cpu.dbr"], counter, s)
end

emu.addMemoryCallback(onExec, emu.callbackType.exec, 0xC19554, 0xC19554,
  emu.cpuType.snes, emu.memType.snesMemory)

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
    local f = io.open(ROOT .. "parser_caller.txt", "w")
    f:write(string.format("parser $C1:9554 entries, f>=1080, count=%d\n\n", #log))
    for _, s in ipairs(log) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end
emu.addEventCallback(onFrame, emu.eventType.endFrame)
