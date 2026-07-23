-- dump_credit_full.lua : 크레딧 화면에서 VRAM·CGRAM·타일맵·PPU·스크린샷 전체 덤프.
--   타일 작업용: 화면 실측 상태를 오프라인으로 재현/대조하기 위함.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/credit_full/"
local CAP = 500  -- 크레딧 표시 구간(f360~f960) 안전 지점

local function dumpMem(name, memType, size)
  local f = io.open(ROOT .. name, "wb")
  if not f then return end
  local t = {}
  for i = 0, size - 1 do
    t[#t + 1] = string.char(emu.read(i, memType))
    if #t == 4096 then f:write(table.concat(t)); t = {} end
  end
  if #t > 0 then f:write(table.concat(t)) end
  f:close()
end

local logged = false
local function logf(msg)
  local f = io.open(ROOT .. "log.txt", "a"); if f then f:write(msg .. "\n"); f:close() end
end
logf("script loaded")

local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  if not logged then logged = true; logf("first frame cb, fr=" .. tostring(fr)) end
  if fr % 100 == 0 then logf("fr=" .. tostring(fr)) end
  if fr >= CAP and not done then
    done = true
    local st = emu.getState()
    dumpMem("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dumpMem("cgram.bin", emu.memType.snesCgRam, 0x200)
    local f = io.open(ROOT .. "ppu.txt", "w")
    if f then
      f:write(string.format("frame=%d bgMode=%s\n", fr, tostring(st["ppu.bgMode"])))
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
    emu.stop(0)
  end
end, emu.eventType.endFrame)
