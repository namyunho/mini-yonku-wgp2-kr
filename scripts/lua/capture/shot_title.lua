-- shot_title.lua : 타이틀 화면 스크린샷(로고 확인).
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/title/"
local FR={1000,1400,1800}
local idx=1
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if idx<=#FR and fr>=FR[idx] then
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."t"..FR[idx]..".png","wb"); if s then s:write(png);s:close() end end
    idx=idx+1
    if idx>#FR then local d=io.open(ROOT.."DONE","w"); if d then d:write("ok");d:close() end; emu.stop(0) end
  end
end, emu.eventType.endFrame)
