-- dump_onmenu.lua : 사용자가 직접 세이브메뉴로 이동. 메뉴 문자열($C0:71B9) 렌더 감지 시
--   VRAM/CGRAM/타일맵/스샷 자동 덤프(매 감지마다 갱신). 입력 주입 안 함 — 순수 관찰.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/"
os.execute('mkdir "C:\\Users\\namyunho\\mini-yonku-wgp2-kr\\tmp\\trace\\menu2" 2>nul')
local pending = nil   -- 덤프 예약 프레임
local count = 0

emu.addMemoryCallback(function()
  if not pending then
    pending = emu.getState()["frameCount"] + 2   -- 렌더 직후 다음 vblank에 덤프
  end
end, emu.callbackType.read, 0xC071B9, 0xC07210, emu.cpuType.snes, emu.memType.snesMemory)

local function dumpMem(name, mt, sz)
  local f = io.open(ROOT .. name, "wb"); if not f then return end
  local t = {}
  for i = 0, sz - 1 do t[#t+1] = string.char(emu.read(i, mt) & 0xFF); if #t == 4096 then f:write(table.concat(t)); t = {} end end
  if #t > 0 then f:write(table.concat(t)) end; f:close()
end

emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  if pending and fr >= pending then
    count = count + 1
    dumpMem("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dumpMem("cgram.bin", emu.memType.snesCgRam, 0x200)
    local st = emu.getState()
    local f = io.open(ROOT .. "ppu.txt", "w")
    f:write(string.format("dump#%d frame=%d bgMode=%s\n", count, fr, tostring(st["ppu.bgMode"])))
    for L = 1, 4 do local p = "ppu.layers[" .. (L-1) .. "]."
      f:write(string.format("BG%d tilemap=%s chr=%s\n", L, tostring(st[p.."tilemapAddress"]), tostring(st[p.."chrAddress"]))) end
    f:close()
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then local s = io.open(ROOT .. "shot.png", "wb"); if s then s:write(png); s:close() end end
    emu.displayMessage("dump", "menu dumped #" .. count .. " @f" .. fr)
    pending = nil
  end
end, emu.eventType.endFrame)
