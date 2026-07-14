-- trace_menudma.lua : 시작 메뉴 폰트/타일맵 DMA 포착 (ROM$C9→VRAM 매핑 확정용).
--   VRAM 목적지 DMA 전부 로그 (src 뱅크·주소, VRAM word addr, size).
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/dma_log.txt"
local f = io.open(OUT, "w")
local count = 0

local function onDma(addr, value)
  local st = emu.getState()
  local fr = st["frameCount"]
  local vmadd = st["ppu.vramAddress"]
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]
      local sb = st[p .. "srcBank"]
      local sa = st[p .. "srcAddress"]
      local size = st[p .. "transferSize"]; if size == 0 then size = 65536 end
      -- VRAM 목적지($2118/$2119)만
      if dest == 0x18 or dest == 0x19 then
        f:write(string.format("f=%-4d ch%d VRAM vmadd=$%04X(tile %d) src=$%02X:%04X size=%d\n",
          fr, ch, vmadd, vmadd // 16, sb, sa, size))
        count = count + 1
      end
    end
  end
  if count % 20 == 0 then f:flush() end
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
  if fr >= 1400 and not done then
    done = true
    f:write("-- total " .. count .. "\n"); f:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
