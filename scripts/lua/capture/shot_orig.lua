local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/title/"
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if fr>=1400 then
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."orig1400.png","wb"); if s then s:write(png);s:close() end end
    local d=io.open(ROOT.."DONEO","w"); if d then d:write("ok");d:close() end; emu.stop(0)
  end
end, emu.eventType.endFrame)
