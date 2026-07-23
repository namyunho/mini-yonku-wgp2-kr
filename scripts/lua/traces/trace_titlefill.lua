-- trace_titlefill.lua : 타이틀 chr($7F:1000)·타일맵($7E:4000) WRAM 버퍼를 채우는 루틴 PC 포착.
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows={}; local seen={}
local function onWrite(addr,value)
  local st=emu.getState(); local fr=st["frameCount"]
  if fr<600 or fr>730 then return end
  local pc=st["cpu.pc"]; local pb=st["cpu.k"]
  local key=pb*0x10000+pc
  if seen[key] then return end
  seen[key]=true
  rows[#rows+1]=string.format("f=%-4d write pc=$%02X:%04X",fr,pb,pc)
end
-- $7F:1000(chr), $7E:4000(tilemap) WRAM 오프셋
emu.addMemoryCallback(onWrite,emu.callbackType.write,0x7F1000,0x7F1010,emu.cpuType.snes,emu.memType.snesMemory)
emu.addMemoryCallback(onWrite,emu.callbackType.write,0x7E4000,0x7E4010,emu.cpuType.snes,emu.memType.snesMemory)
emu.addEventCallback(function()
  if emu.getState()["frameCount"]>=730 then
    local f=io.open(ROOT.."titlefill.txt","w")
    for _,s in ipairs(rows) do f:write(s.."\n") end; f:close(); emu.stop(0)
  end
end, emu.eventType.endFrame)
