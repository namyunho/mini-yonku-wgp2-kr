-- trace_lzptr.lua : LZSS 소스 롱포인터 셋업 위치 규명.
--   DP $0013(소스 뱅크바이트)에 $C7을 쓰는 PC, 그리고 $0011/$0012(주소) 쓰는 PC 포착.
--   → 재배치 시 패치할 포인터 셋업 명령/오퍼랜드 확정. 산출 tmp/trace/lz_ptr.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows = {}
local function log(tag, addr, value)
  local st = emu.getState()
  rows[#rows + 1] = string.format("f=%-4d PC=$%02X:%04X %s $00:%04X=%02X (a=%04X x=%04X)",
    st["frameCount"], st["cpu.k"], st["cpu.pc"], tag, addr, value, st["cpu.a"], st["cpu.x"])
end
-- $13 에 C7 쓰는 경우만(소스뱅크 세팅)
emu.addMemoryCallback(function(addr, value)
  if value == 0xC7 then log("STbank", addr, value) end
end, emu.callbackType.write, 0x000013, 0x000013, emu.cpuType.snes, emu.memType.snesMemory)
-- $11 (주소 하위) 쓰기도 포착
emu.addMemoryCallback(function(addr, value)
  log("ST11", addr, value)
end, emu.callbackType.write, 0x000011, 0x000011, emu.cpuType.snes, emu.memType.snesMemory)

local done = false
emu.addEventCallback(function()
  if emu.getState()["frameCount"] == 200 and not done then
    done = true
    local f = io.open(ROOT .. "lz_ptr.txt", "w")
    if f then for _, s in ipairs(rows) do f:write(s .. "\n") end; f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
