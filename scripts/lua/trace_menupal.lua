-- trace_menupal.lua : 세이브메뉴 렌더 글자별 base(팔레트)·tileval 파악.
--   내 렌더러 훅 진입 $C1:9843에서 base($07=DP+7)·tileval($05)·X 로그.
--   메뉴 문자열 읽힘 이후 한정.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/menupal.txt"
local rows = {}
local armed = false
local function flush() local f=io.open(OUT,"w"); for _,s in ipairs(rows) do f:write(s.."\n") end; f:close() end

emu.addMemoryCallback(function()
  armed = true
end, emu.callbackType.read, 0xC071B9, 0xC071C0, emu.cpuType.snes, emu.memType.snesMemory)

emu.addMemoryCallback(function()
  if not armed or #rows >= 60 then return end
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r16(a) return emu.read(d+a, emu.memType.snesWorkRam) + emu.read(d+a+1, emu.memType.snesWorkRam)*256 end
  rows[#rows+1] = string.format("tileval($05)=%04X base($07)=%04X X=%04X",
    r16(5), r16(7), st["cpu.x"])
  flush()
end, emu.callbackType.exec, 0xC19843, 0xC19843, emu.cpuType.snes, emu.memType.snesMemory)
