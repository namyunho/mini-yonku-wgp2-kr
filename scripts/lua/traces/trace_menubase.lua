-- trace_menubase.lua : 세이브메뉴($C0:71B9) 렌더 base·타일 확정 (READ 콜백 기반).
--   $C0:71B9-7210 READ 콜백(작동확인됨) 발화 시, PC가 렌더러 내부($C1:96xx)면
--   DP+7 워드(=base $07)·Y·읽은주소 로그. READ 콜백은 exec와 달리 확실히 발화.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/base_trace.txt"
local samp = {}
local seen = {}

emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
  -- 렌더러 $C1:965E~96B8 내부에서의 읽기만
  if pc >= 0xC19666 and pc <= 0xC196B0 then
    local d = st["cpu.d"]
    local base = emu.read(d + 7, emu.memType.snesWorkRam) + emu.read(d + 8, emu.memType.snesWorkRam) * 256
    local key = string.format("%04X", base)
    if not seen[key] and #samp < 20 then
      seen[key] = true
      samp[#samp+1] = string.format("read addr=$%06X val=%02X  PC=$%06X  Y=%04X  DBR=%02X  DP=%04X  base($07)=%04X",
        addr, value, pc, st["cpu.y"], st["cpu.db"], d, base)
    end
  end
end, emu.callbackType.read, 0xC071B9, 0xC07210, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  press("start", (fr % 90) < 5)
  if fr >= 1500 and not done then
    done = true
    local f = io.open(OUT, "w")
    f:write("# samples=" .. #samp .. "\n")
    for _, s in ipairs(samp) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
