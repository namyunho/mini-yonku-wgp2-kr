-- shot_seq.lua : 크레딧 구간 여러 프레임 스크린샷 연속 캡처(애니메이션 깨짐 확인용).
local ROOT="C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/seq/"
local FRAMES={365,375,385,400,430,470,520,580,650,750}
local idx=1
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if idx<=#FRAMES and fr>=FRAMES[idx] then
    local ok,png=pcall(function() return emu.takeScreenshot() end)
    if ok and type(png)=="string" then local s=io.open(ROOT.."f"..FRAMES[idx]..".png","wb"); if s then s:write(png);s:close() end end
    idx=idx+1
    if idx>#FRAMES then local d=io.open(ROOT.."DONE","w"); if d then d:write("ok");d:close() end; emu.stop(0) end
  end
end, emu.eventType.endFrame)
