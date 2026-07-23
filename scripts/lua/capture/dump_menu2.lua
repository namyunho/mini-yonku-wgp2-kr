-- dump_menu2.lua : 세이브메뉴(はじめから)가 확실히 떠있는 frame 1120에 VRAM/타일맵/CGRAM/스샷 덤프.
--   shot_menu와 동일 입력패턴(매 90프레임 start). 1120에서 스냅.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/"
os.execute('mkdir "C:\\Users\\namyunho\\mini-yonku-wgp2-kr\\tmp\\trace\\menu2" 2>nul')
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
  press("start", (fr % 90) < 5)
  -- 여러 시점 스샷으로 메뉴 확인
  if (fr == 1040 or fr == 1120 or fr == 1200) then
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then local s = io.open(ROOT .. "shot_" .. fr .. ".png", "wb"); if s then s:write(png); s:close() end end
  end
  if fr == 1120 and not done then
    done = true
    dumpMem("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dumpMem("cgram.bin", emu.memType.snesCgRam, 0x200)
    local st = emu.getState()
    local f = io.open(ROOT .. "ppu.txt", "w")
    f:write("frame=" .. fr .. " bgMode=" .. tostring(st["ppu.bgMode"]) .. "\n")
    for L = 1, 4 do local p = "ppu.layers[" .. (L-1) .. "]."
      f:write(string.format("BG%d tilemap=%s chr=%s\n", L, tostring(st[p.."tilemapAddress"]), tostring(st[p.."chrAddress"]))) end
    f:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
