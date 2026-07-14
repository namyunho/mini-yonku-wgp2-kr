-- trace_lzcaller.lua : LZSS 디컴프 진입 $C0:0D91 에서 DP·호출자(복귀주소) 포착.
--   → 소스포인터가 실제 저장된 DP 위치와, 그걸 세팅하는 호출자 코드 규명.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows = {}
emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"]; local s = st["cpu.s"]
  -- 복귀주소: JSL이면 스택 top3(하위→상위, +1바이트 오프셋), JSR이면 top2.
  local b1 = emu.read(s + 1, emu.memType.snesWorkRam)
  local b2 = emu.read(s + 2, emu.memType.snesWorkRam)
  local b3 = emu.read(s + 3, emu.memType.snesWorkRam)
  -- 소스포인터(현재 DP 기준)
  local pl = emu.read(d + 0x11, emu.memType.snesWorkRam)
  local pm = emu.read(d + 0x12, emu.memType.snesWorkRam)
  local pb = emu.read(d + 0x13, emu.memType.snesWorkRam)
  rows[#rows + 1] = string.format(
    "f=%-4d D=$%04X S=$%04X ret(JSL)=$%02X:%04X src=$%02X:%04X",
    st["frameCount"], d, s, b3, b2 * 256 + b1, pb, pm * 256 + pl)
end, emu.callbackType.exec, 0xC00D91, 0xC00D91, emu.cpuType.snes, emu.memType.snesMemory)

local done = false
emu.addEventCallback(function()
  if emu.getState()["frameCount"] == 200 and not done then
    done = true
    local f = io.open(ROOT .. "lz_caller.txt", "w")
    if f then for _, s in ipairs(rows) do f:write(s .. "\n") end; f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
