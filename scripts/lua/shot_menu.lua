-- shot_menu.lua : 타이틀 이후 시작 메뉴(はじめから 등) 화면 포착 + SJIS 읽기 훅.
--   주기적 Start로 타이틀→메뉴 진행. $C0:71B9(메뉴 SJIS) READ PC도 집계.
--   산출: tmp/trace/menu/menu_<fr>.png, tmp/trace/menu_read.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/"
local reads = {}
emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
  reads[pc] = (reads[pc] or 0) + 1
end, emu.callbackType.read, 0xC071B9, 0xC07210, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  local on = (fr % 90) < 5
  press("start", on)
  if fr >= 500 and fr % 80 == 0 then
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then
      local s = io.open(ROOT .. "menu_" .. fr .. ".png", "wb"); if s then s:write(png); s:close() end
    end
  end
  if fr >= 1800 and not done then
    done = true
    local f = io.open("C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu_read.txt", "w")
    if f then f:write("# $C0:71B9-7210 READ PC\n")
      for pc, n in pairs(reads) do f:write(string.format("PC=$%02X:%04X n=%d\n", pc >> 16, pc & 0xFFFF, n)) end
      f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
