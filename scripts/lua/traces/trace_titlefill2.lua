-- trace_titlefill2.lua : 타이틀 chr/타일맵 버퍼 '중간'을 쓰는 벌크 루틴 PC 포착.
--   $7F:2000(chr 중간), $7E:4800(타일맵 중간). 파라미터 셋업($7F:1000) 아닌 실제 디컴프 필러.
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows={}; local seen={}
local function onWrite(addr,value)
  local st=emu.getState(); local fr=st["frameCount"]
  if fr>760 then return end
  local pc=st["cpu.pc"]; local pb=st["cpu.k"]
  local key=pb*0x10000+pc
  if seen[key] then return end
  seen[key]=true
  rows[#rows+1]=string.format("f=%-4d addr=%06X write pc=$%02X:%04X",fr,addr,pb,pc)
end
emu.addMemoryCallback(onWrite,emu.callbackType.write,0x7F2000,0x7F2003,emu.cpuType.snes,emu.memType.snesMemory)
emu.addMemoryCallback(onWrite,emu.callbackType.write,0x7E4800,0x7E4803,emu.cpuType.snes,emu.memType.snesMemory)
emu.addEventCallback(function()
  if emu.getState()["frameCount"]>=760 then
    local f=io.open(ROOT.."titlefill2.txt","w")
    for _,s in ipairs(rows) do f:write(s.."\n") end; f:close(); emu.stop(0)
  end
end, emu.eventType.endFrame)
