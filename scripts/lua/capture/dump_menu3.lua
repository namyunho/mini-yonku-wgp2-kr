-- dump_menu3.lua : 메뉴 문자열($C0:71B9) 읽힘 감지 → 입력 중단(메뉴 고정) → VRAM 덤프.
--   메뉴 렌더 시 $C1:965E가 $C0:71B9를 읽음. 그 프레임+20에 VRAM/CGRAM/타일맵/스샷 덤프.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/"
os.execute('mkdir "C:\\Users\\namyunho\\mini-yonku-wgp2-kr\\tmp\\trace\\menu2" 2>nul')
local menuFrame = nil
emu.addMemoryCallback(function(addr, value)
  if not menuFrame then
    menuFrame = emu.getState()["frameCount"]
  end
end, emu.callbackType.read, 0xC071B9, 0xC07210, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end
local function dumpMem(name, mt, sz)
  local f = io.open(ROOT .. name, "wb"); if not f then return end
  local t = {}
  for i = 0, sz - 1 do t[#t+1] = string.char(emu.read(i, mt) & 0xFF); if #t == 4096 then f:write(table.concat(t)); t = {} end end
  if #t > 0 then f:write(table.concat(t)) end; f:close()
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  -- shot_menu와 동일하게 계속 start 펄스(메뉴 렌더 재현). 첫 읽힘 직후 즉시 덤프.
  press("start", (fr % 90) < 5)
  if menuFrame and fr >= menuFrame + 2 and not done then
    done = true
    dumpMem("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dumpMem("cgram.bin", emu.memType.snesCgRam, 0x200)
    local st = emu.getState()
    local f = io.open(ROOT .. "ppu.txt", "w")
    f:write(string.format("menuFrame=%d dumpFrame=%d bgMode=%s\n", menuFrame, fr, tostring(st["ppu.bgMode"])))
    for L = 1, 4 do local p = "ppu.layers[" .. (L-1) .. "]."
      f:write(string.format("BG%d tilemap=%s chr=%s\n", L, tostring(st[p.."tilemapAddress"]), tostring(st[p.."chrAddress"]))) end
    f:close()
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then local s = io.open(ROOT .. "shot.png", "wb"); if s then s:write(png); s:close() end end
    emu.stop(0)
  end
  if fr > 3000 and not done then done = true; emu.stop(0) end
end, emu.eventType.endFrame)
