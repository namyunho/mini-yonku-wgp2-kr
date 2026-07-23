-- trace_chrsrc.lua : 타이틀 chr LZSS 디컴프 소스 포인터 캡처.
--   $C0:0DC1(디컴프 store) 타이틀구간 첫 히트에서 DP $11-$13(소스 롱포인터)·$05(길이) 읽음.
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows={}; local last=nil
local function onExec()
  local st=emu.getState(); local fr=st["frameCount"]
  if fr<650 then return end
  local d=st["cpu.d"]
  local function r(a) return emu.read(d+a,emu.memType.snesWorkRam) end
  local lo,mi,bk=r(0x11),r(0x12),r(0x13)
  local len=r(0x05)+r(0x06)*256
  local s=string.format("f=%-4d src=$%02X:%04X(pc=0x%06X) len=%d D=%04X",fr,bk,mi*256+lo,((bk%0x40)*0x10000)+(mi*256+lo),len,d)
  if s~=last then rows[#rows+1]=s; last=s end
end
emu.addMemoryCallback(onExec,emu.callbackType.exec,0xC00DC1,0xC00DC1,emu.cpuType.snes,emu.memType.snesMemory)
emu.addEventCallback(function()
  if emu.getState()["frameCount"]>=700 then
    local f=io.open(ROOT.."chrsrc.txt","w")
    for i=1,math.min(#rows,30) do f:write(rows[i].."\n") end
    f:write("...total "..#rows.."\n"); f:close(); emu.stop(0)
  end
end, emu.eventType.endFrame)
