-- dump_credit_mid.lua : 크레딧 중앙 프레임(450) 무조건 전체 덤프 + getState 전체 키 저장.
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/credit2/"
local CAP=450
local function dumpMem(name,mt,size)
  local f=io.open(ROOT..name,"wb"); if not f then return end
  local t={}
  for i=0,size-1 do t[#t+1]=string.char(emu.read(i,mt)); if #t==4096 then f:write(table.concat(t));t={} end end
  if #t>0 then f:write(table.concat(t)) end; f:close()
end
local done=false
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if fr>=CAP and not done then
    done=true
    local st=emu.getState()
    dumpMem("vram.bin",emu.memType.snesVideoRam,0x10000)
    dumpMem("cgram.bin",emu.memType.snesCgRam,0x200)
    dumpMem("oam.bin",emu.memType.snesSpriteRam,0x220)
    -- getState 전체 키 덤프
    local keys={}
    for k,v in pairs(st) do keys[#keys+1]=tostring(k).."="..tostring(v) end
    table.sort(keys)
    local f=io.open(ROOT.."state.txt","w"); if f then f:write("frame="..fr.."\n"..table.concat(keys,"\n")); f:close() end
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."screen.png","wb"); if s then s:write(png);s:close() end end
    local d=io.open(ROOT.."DONE","w"); if d then d:write(tostring(fr)); d:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
