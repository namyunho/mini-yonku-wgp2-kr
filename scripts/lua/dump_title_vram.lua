local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/title/"
local function dumpMem(name,mt,size)
  local f=io.open(ROOT..name,"wb"); if not f then return end
  local t={}
  for i=0,size-1 do t[#t+1]=string.char(emu.read(i,mt)); if #t==4096 then f:write(table.concat(t));t={} end end
  if #t>0 then f:write(table.concat(t)) end; f:close()
end
local done=false
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if fr>=1400 and not done then
    done=true
    dumpMem("vram.bin",emu.memType.snesVideoRam,0x10000)
    dumpMem("cgram.bin",emu.memType.snesCgRam,0x200)
    local st=emu.getState()
    local f=io.open(ROOT.."ppu.txt","w")
    f:write("frame="..fr.." mainScreen="..tostring(st["ppu.mainScreenLayers"]).."\n")
    for L=1,4 do local p="ppu.layers["..(L-1).."]."
      f:write(string.format("BG%d tm=%s chr=%s hs=%s vs=%s\n",L,tostring(st[p.."tilemapAddress"]),tostring(st[p.."chrAddress"]),tostring(st[p.."hscroll"]),tostring(st[p.."vscroll"]))) end
    f:close()
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok then local s=io.open(ROOT.."vshot.png","wb"); if s then s:write(png);s:close() end end
    local d=io.open(ROOT.."DONEV","w"); d:write("ok");d:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
