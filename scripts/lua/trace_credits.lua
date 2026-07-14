-- trace_credits.lua : 오프닝 크레딧 화면(부팅 후 ~f400)에서 그래픽 자원 덤프.
--   VRAM(64KB)·CGRAM(512B)·PPU 레이어 레지스터·스크린샷 → 오프라인 렌더/역추적용.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/credits/"
local CAP = 420

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

local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
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
        f:write(string.format("BG%d tilemap=%s chr=%s doubleW=%s doubleH=%s\n", L,
          tostring(st[p .. "tilemapAddress"]), tostring(st[p .. "chrAddress"]),
          tostring(st[p .. "doubleWidth"]), tostring(st[p .. "doubleHeight"])))
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
