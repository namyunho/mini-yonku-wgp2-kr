local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/title/"
local FR={}; for f=900,2600,60 do FR[#FR+1]=f end
local idx=1
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if idx<=#FR and fr>=FR[idx] then
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."s"..FR[idx]..".png","wb"); if s then s:write(png);s:close() end end
    idx=idx+1
    if idx>#FR then local d=io.open(ROOT.."DONE2","w"); if d then d:write("ok");d:close() end; emu.stop(0) end
  end
end, emu.eventType.endFrame)
