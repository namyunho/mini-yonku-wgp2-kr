-- trace_menuwriter.lua : 메뉴 폰트 스테이징 $7F:1000 버퍼를 채우는 주체(PC) 추적.
--   $7F:1080(폰트 비어있지않은 영역)에 쓰는 명령의 PC·프레임 로그. 폰트 로더 특정.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/writer.txt"
local rows = {}
local seen = {}
emu.addMemoryCallback(function(addr, value)
  if #rows >= 40 then return end
  local st = emu.getState()
  local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
  local key = pc
  if not seen[key] then
    seen[key] = true
    rows[#rows+1] = string.format("f=%-4d PC=$%06X addr=$%06X val=%02X  X=%04X Y=%04X DBR=%02X",
      st["frameCount"], pc, 0x7F1080, value, st["cpu.x"], st["cpu.y"], st["cpu.db"])
  end
end, emu.callbackType.write, 0x7F1080, 0x7F1080, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  press("start", (fr % 90) < 5)
  if fr >= 1100 and not done then
    done = true
    local f = io.open(OUT, "w")
    f:write("# $7F:1080 writers\n")
    for _, s in ipairs(rows) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
