-- dump_menufont.lua : 메뉴 폰트 VRAM DMA(vmadd=$1000, tile256) 순간에 소스 $7F:1000
--   버퍼(4096B)를 그대로 덤프. → ROM에서 (압축/비압축) 소스 역추적용.
--   또 최종 VRAM(타일 0x100~ 폰트)도 덤프.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/"
local dumped = false

local function dumpWram(name, srcbank, srcaddr, size)
  local f = io.open(ROOT .. name, "wb"); if not f then return end
  local base = srcbank * 0x10000 + srcaddr
  local t = {}
  for i = 0, size - 1 do
    t[#t+1] = string.char(emu.read(base + i, emu.memType.snesMemory) & 0xFF)
    if #t == 4096 then f:write(table.concat(t)); t = {} end
  end
  if #t > 0 then f:write(table.concat(t)) end
  f:close()
end

local function onDma(addr, value)
  if dumped then return end
  local st = emu.getState()
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]
      local vmadd = st["ppu.vramAddress"]
      -- 메뉴 폰트 DMA: VRAM 목적지 & vmadd word=0x1000 (tile 256)
      if (dest == 0x18 or dest == 0x19) and vmadd == 0x1000 then
        local sb = st[p .. "srcBank"]; local sa = st[p .. "srcAddress"]
        local size = st[p .. "transferSize"]; if size == 0 then size = 65536 end
        dumpWram("menufont_src.bin", sb, sa, size)
        local lf = io.open(ROOT .. "menufont_src.txt", "w")
        lf:write(string.format("src=$%02X:%04X size=%d frame=%d vmadd_tile=256\n", sb, sa, size, st["frameCount"]))
        lf:close()
        dumped = true
      end
    end
  end
end
emu.addMemoryCallback(onDma, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  press("start", (fr % 90) < 5)
  if fr >= 1300 and not done then
    done = true
    -- VRAM 폰트 영역도 덤프
    local f = io.open(ROOT .. "vram_menu.bin", "wb")
    if f then
      local t = {}
      for i = 0, 0xFFFF do t[#t+1] = string.char(emu.read(i, emu.memType.snesVideoRam) & 0xFF); if #t==4096 then f:write(table.concat(t)); t={} end end
      if #t>0 then f:write(table.concat(t)) end; f:close()
    end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
