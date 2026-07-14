-- trace_kordma.lua : 패치 ROM에서 한글 DMA(VRAM word 0x1500=tile672) 및 폰트 DMA 추적.
--   또 내 인젝트 루틴 $C1:9940 실행 여부(exec) 확인.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/kordma.txt"
local rows = {}
local injectRan = 0
local function flush() local f=io.open(OUT,"w"); f:write("inject $C1:9940 exec="..injectRan.."\n"); for _,s in ipairs(rows) do f:write(s.."\n") end; f:close() end

emu.addMemoryCallback(function()
  injectRan = injectRan + 1; flush()
end, emu.callbackType.exec, 0xC19940, 0xC19940, emu.cpuType.snes, emu.memType.snesMemory)

emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  local vmadd = st["ppu.vramAddress"]
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]
      if (dest == 0x18 or dest == 0x19) then
        local sb=st[p.."srcBank"]; local sa=st[p.."srcAddress"]
        local size=st[p.."transferSize"]; if size==0 then size=65536 end
        local vt = vmadd // 8
        local endtile = vt + size//16
        rows[#rows+1]=string.format("f=%d ch%d VRAMtile %d-%d src=$%02X:%04X size=%d",
          st["frameCount"], ch, vt, endtile, sb, sa, size)
        flush()
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)
