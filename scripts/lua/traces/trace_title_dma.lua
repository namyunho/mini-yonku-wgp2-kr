-- trace_title_dma.lua : 타이틀 화면(~f3400)까지 VRAM DMA만 기록(BG1 타일맵 $5000 소스 추적).
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local f=io.open(ROOT.."title_dma.txt","w")
local STOP=3500
local function onDma(addr,value)
  local st=emu.getState(); local fr=st["frameCount"]
  local vmadd=st["ppu.vramAddress"]
  for ch=0,7 do
    if (value&(1<<ch))~=0 then
      local p="dmaController.channel["..ch.."]."
      local dest=st[p.."destAddress"]; local sb=st[p.."srcBank"]; local sa=st[p.."srcAddress"]
      local size=st[p.."transferSize"]; local rs=(size==0) and 65536 or size
      -- VRAM(0x18/0x19)만, 그리고 OAM 스팸 제외
      if dest==0x18 or dest==0x19 then
        f:write(string.format("f=%-5d %02X:%04X size=%-6d vmadd=$%04X\n",fr,sb,sa,rs,vmadd)); f:flush()
      end
    end
  end
  if st["frameCount"]>=STOP then f:close(); emu.stop(0) end
end
emu.addMemoryCallback(onDma,emu.callbackType.write,0x420B,0x420B,emu.cpuType.snes,emu.memType.snesMemory)
emu.addEventCallback(function()
  if emu.getState()["frameCount"]>=STOP then f:close(); emu.stop(0) end
end, emu.eventType.endFrame)
