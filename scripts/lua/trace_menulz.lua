-- trace_menulz.lua : 메뉴 도달까지 LZSS 디컴프($C0:0D91) 진입 전부 캡처.
--   소스 롱포인터($11-$13)·길이($05)·프레임. Start 눌러 메뉴 진행. → 메뉴 폰트 소스 특정.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/lz_src.txt"
local rows = {}
emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r(a) return emu.read(d + a, emu.memType.snesWorkRam) end
  local lo, mi, bk = r(0x11), r(0x12), r(0x13)
  local len = r(0x05) + r(0x06) * 256
  rows[#rows+1] = string.format("f=%-4d src=$%02X:%04X len=%d", st["frameCount"], bk, mi*256+lo, len)
end, emu.callbackType.exec, 0xC00D91, 0xC00D91, emu.cpuType.snes, emu.memType.snesMemory)

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
    f:write("# LZSS 디컴프 진입 (메뉴 도달까지)\n")
    for _, s in ipairs(rows) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
