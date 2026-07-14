-- trace_menurender.lua : 타이틀 메뉴 실렌더 경로 확정.
--   두 후보 렌더러 진입을 카운트: $C1:965E(SJIS변환), $C0:1B4B(직접타일).
--   또 $C1:965E 진입 시 문자열포인터(Y)와 첫 변환결과를 로그.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu/"
local cnt = { c1965e = 0, c01b4b = 0 }
local samples = {}
emu.addMemoryCallback(function()
  cnt.c1965e = cnt.c1965e + 1
  if #samples < 12 then
    local st = emu.getState()
    samples[#samples+1] = string.format("$C1:965E y=%04X d=%04X $07=%04X", st["cpu.y"], st["cpu.d"],
      emu.read(st["cpu.d"]+7, emu.memType.snesWorkRam) + emu.read(st["cpu.d"]+8, emu.memType.snesWorkRam)*256)
  end
end, emu.callbackType.exec, 0xC1965E, 0xC1965E, emu.cpuType.snes, emu.memType.snesMemory)
emu.addMemoryCallback(function()
  cnt.c01b4b = cnt.c01b4b + 1
end, emu.callbackType.exec, 0xC01B4B, 0xC01B4B, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn,on)
  local ok=pcall(function() emu.setInput(1,{[btn]=on}) end)
  if not ok then pcall(function() emu.setInput(1,0,{[btn]=on}) end) end
end
local done=false
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  press("start",(fr%90)<5)
  if fr>=1400 and not done then
    done=true
    local f=io.open(ROOT.."render_path.txt","w")
    if f then f:write(string.format("$C1:965E(SJIS) hits=%d  $C0:1B4B(직접) hits=%d\n\n",cnt.c1965e,cnt.c01b4b))
      for _,s in ipairs(samples) do f:write(s.."\n") end; f:close() end
    emu.stop(0)
  end
end,emu.eventType.endFrame)
