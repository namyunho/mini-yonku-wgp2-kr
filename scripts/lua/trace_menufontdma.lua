-- trace_menufontdma.lua : 메뉴 폰트(VRAM tile 256 = word 0x800)로 가는 DMA를 정확히 포착.
--   목적: DMA 크기·소스·목적지 확인 → 확장 시 크기 패치 대상 특정. 사용자 수동 메뉴 이동.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/fontdma.txt"
local rows = {}
local function flush() local f=io.open(OUT,"w"); for _,s in ipairs(rows) do f:write(s.."\n") end; f:close() end

emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  local vmadd = st["ppu.vramAddress"]
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]
      if (dest == 0x18 or dest == 0x19) then
        local sb = st[p .. "srcBank"]; local sa = st[p .. "srcAddress"]
        local size = st[p .. "transferSize"]; if size == 0 then size = 65536 end
        local vt = vmadd // 8   -- 2bpp: tile = word/8
        -- VRAM tile 200~320 목적지(메뉴 폰트 영역 tile 256 부근)만
        if vt >= 180 and vt <= 400 then
          rows[#rows+1] = string.format("f=%d ch%d VRAMword=$%04X(tile %d) src=$%02X:%04X size=%d(%d타일)",
            st["frameCount"], ch, vmadd, vt, sb, sa, size, size//16)
          flush()
        end
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)
