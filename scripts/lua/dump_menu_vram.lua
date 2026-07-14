-- dump_menu_vram.lua : 시작 메뉴 화면(~f1200)에서 VRAM·CGRAM 덤프 (메뉴 폰트 확인용).
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/"
local function press(btn,on)
  local ok=pcall(function() emu.setInput(1,{[btn]=on}) end)
  if not ok then pcall(function() emu.setInput(1,0,{[btn]=on}) end) end
end
local function dumpMem(name,mt,sz)
  local f=io.open(ROOT..name,"wb"); if not f then return end
  local t={}
  for i=0,sz-1 do t[#t+1]=string.char(emu.read(i,mt)); if #t==4096 then f:write(table.concat(t)); t={} end end
  if #t>0 then f:write(table.concat(t)) end; f:close()
end
local done=false
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  press("start",(fr%90)<5)
  if fr>=1250 and not done then
    done=true
    dumpMem("vram.bin",emu.memType.snesVideoRam,0x10000)
    dumpMem("cgram.bin",emu.memType.snesCgRam,0x200)
    local st=emu.getState()
    local f=io.open(ROOT.."ppu.txt","w")
    if f then f:write("bgMode="..tostring(st["ppu.bgMode"]).."\n")
      for L=1,4 do local p="ppu.layers["..(L-1).."]."
        f:write(string.format("BG%d tilemap=%s chr=%s\n",L,tostring(st[p.."tilemapAddress"]),tostring(st[p.."chrAddress"]))) end
      f:close() end
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."menu_state.png","wb"); if s then s:write(png); s:close() end end
    emu.stop(0)
  end
end,emu.eventType.endFrame)
