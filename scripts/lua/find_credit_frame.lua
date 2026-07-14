-- find_credit_frame.lua : 크레딧 글리프(VRAM 0x7000대) 로드 프레임 탐지 + 그 시점 전체 덤프.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/credit2/"
local function logf(m) local f=io.open(ROOT.."log.txt","a"); if f then f:write(m.."\n"); f:close() end end
local function dumpMem(name, mt, size)
  local f=io.open(ROOT..name,"wb"); if not f then return end
  local t={}
  for i=0,size-1 do t[#t+1]=string.char(emu.read(i,mt)); if #t==4096 then f:write(table.concat(t));t={} end end
  if #t>0 then f:write(table.concat(t)) end; f:close()
end
local function nz7000()
  local n=0
  for i=0x7000,0x8FFF do if emu.read(i,emu.memType.snesVideoRam)~=0 then n=n+1 end end
  return n
end
local best=-1; local bestfr=0; local dumped=false
logf("start")
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if fr<340 or fr>620 then return end
  local n=nz7000()
  if fr%10==0 then logf("fr="..fr.." nz7000="..n) end
  if n>best then best=n; bestfr=fr end
  -- 0x7000이 충분히 채워진 첫 안정 프레임에서 덤프
  if n>2000 and not dumped then
    dumped=true
    logf("DUMP at fr="..fr.." nz7000="..n)
    local st=emu.getState()
    dumpMem("vram.bin",emu.memType.snesVideoRam,0x10000)
    dumpMem("cgram.bin",emu.memType.snesCgRam,0x200)
    local f=io.open(ROOT.."ppu.txt","w")
    if f then
      f:write(string.format("frame=%d bgMode=%s\n",fr,tostring(st["ppu.bgMode"])))
      for L=1,4 do local p="ppu.layers["..(L-1).."]."
        f:write(string.format("BG%d tilemap=%s chr=%s dW=%s\n",L,tostring(st[p.."tilemapAddress"]),tostring(st[p.."chrAddress"]),tostring(st[p.."doubleWidth"]))) end
      f:close()
    end
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."screen.png","wb"); if s then s:write(png);s:close() end end
    local d=io.open(ROOT.."DONE","w"); if d then d:write(tostring(fr)); d:close() end
    emu.stop(0)
  end
  if fr>=615 and not dumped then logf("NO DUMP; best nz7000="..best.." at fr="..bestfr); emu.stop(0) end
end, emu.eventType.endFrame)
