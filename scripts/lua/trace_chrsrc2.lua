-- trace_chrsrc2.lua : chr 버퍼 초반 write 순간의 소스포인터 $11-$13 캡처(write콜백 경유).
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows={}; local seen={}
local function onW(addr,value)
  local st=emu.getState(); local fr=st["frameCount"]
  if fr<650 then return end
  local pc=st["cpu.k"]*0x10000+st["cpu.pc"]
  local d=st["cpu.d"]
  local function r(a) return emu.read(d+a,emu.memType.snesWorkRam) end
  local key=addr
  if seen[key] then return end
  seen[key]=true
  rows[#rows+1]=string.format("f=%-4d w=%06X pc=%06X src=$%02X:%04X len=%d D=%04X out05=%02X%02X",
    fr,addr,pc,r(0x13),r(0x12)*256+r(0x11),r(0x05)+r(0x06)*256,d,r(0x08),r(0x07))
end
for _,a in ipairs({0x7F1008,0x7F1010,0x7F1020,0x7F1040}) do
  emu.addMemoryCallback(onW,emu.callbackType.write,a,a,emu.cpuType.snes,emu.memType.snesWorkRam)
end
emu.addEventCallback(function()
  if emu.getState()["frameCount"]>=700 then
    local f=io.open(ROOT.."chrsrc2.txt","w")
    for _,s in ipairs(rows) do f:write(s.."\n") end; f:close(); emu.stop(0)
  end
end, emu.eventType.endFrame)
