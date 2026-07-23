-- dump_live.lua : 트리거 파일 신호로 현재 화면 상태를 덤프(신호 기반 대화형).
--   사용: 원하는 화면 도달 → tmp/trace/live/DUMP 파일 생성 → 다음 프레임에 덤프 후 DONE 기록.
--   ※ 일시정지 중엔 endFrame이 안 돌아 덤프 안 됨 → 프레임 어드밴스 1회로 트리거.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/live/"
local TRIG = ROOT .. "DUMP"
local DONE = ROOT .. "DONE"

local function exists(p) local f = io.open(p, "rb"); if f then f:close(); return true end; return false end
local function rm(p) os.remove(p) end

local function dumpMem(name, memType, size)
  local f = io.open(ROOT .. name, "wb"); if not f then return end
  local t = {}
  for i = 0, size - 1 do
    t[#t + 1] = string.char(emu.read(i, memType))
    if #t == 4096 then f:write(table.concat(t)); t = {} end
  end
  if #t > 0 then f:write(table.concat(t)) end
  f:close()
end

emu.addEventCallback(function()
  if not exists(TRIG) then return end
  rm(TRIG); rm(DONE)
  local st = emu.getState()
  dumpMem("vram.bin", emu.memType.snesVideoRam, 0x10000)
  dumpMem("cgram.bin", emu.memType.snesCgRam, 0x200)
  dumpMem("oam.bin", emu.memType.snesSpriteRam, 0x220)
  local f = io.open(ROOT .. "ppu.txt", "w")
  if f then
    f:write(string.format("frame=%s bgMode=%s\n", tostring(st["frameCount"]), tostring(st["ppu.bgMode"])))
    for L = 1, 4 do
      local p = "ppu.layers[" .. (L - 1) .. "]."
      f:write(string.format("BG%d tilemap=%s chr=%s doubleW=%s doubleH=%s hscroll=%s vscroll=%s\n", L,
        tostring(st[p .. "tilemapAddress"]), tostring(st[p .. "chrAddress"]),
        tostring(st[p .. "doubleWidth"]), tostring(st[p .. "doubleHeight"]),
        tostring(st[p .. "hScroll"]), tostring(st[p .. "vScroll"])))
    end
    f:close()
  end
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local s = io.open(ROOT .. "screen.png", "wb"); if s then s:write(png); s:close() end
  end
  local d = io.open(DONE, "w"); if d then d:write(tostring(st["frameCount"])); d:close() end
  emu.displayMessage("Lua", "dumped frame " .. tostring(st["frameCount"]))
end, emu.eventType.endFrame)

emu.displayMessage("Lua", "dump_live ready")
