-- trace_sjis.lua : 타이틀 메뉴(SJIS $C0:71B9~)를 읽는 렌더러/복사 루틴을 규명.
--   메뉴 문자열 바이트를 READ 하는 PC를 집계 → SJIS 폰트 경로 추적의 출발점.
--   부팅 후 스타트 눌러 타이틀 메뉴 진입. 산출: tmp/trace/sjis_read.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local LO, HI = 0xC071B9, 0xC07210      -- 타이틀 메뉴 SJIS 영역(SNES 주소)

local agg = {}      -- pc -> {n, sampleA, sampleX, sampleY, dbr, minAddr, maxAddr}
local order = {}

local function onRead(addr, value)
  local st = emu.getState()
  local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
  local e = agg[pc]
  if not e then
    e = { n = 0, a = st["cpu.a"], x = st["cpu.x"], y = st["cpu.y"],
          d = st["cpu.d"], dbr = st["cpu.dbr"], minA = addr, maxA = addr,
          fr = st["frameCount"] }
    agg[pc] = e; order[#order + 1] = pc
  end
  e.n = e.n + 1
  if addr < e.minA then e.minA = addr end
  if addr > e.maxA then e.maxA = addr end
end
emu.addMemoryCallback(onRead, emu.callbackType.read, LO, HI, emu.cpuType.snes, emu.memType.snesMemory)

-- 부팅 후 스타트 연타로 타이틀 메뉴 진입
local function pressStart(on)
  local ok = pcall(function() emu.setInput(1, { start = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { start = on }) end) end
end

local done = false
local function dump()
  local f = io.open(ROOT .. "sjis_read.txt", "w")
  if not f then return end
  f:write("# 타이틀 메뉴 $C0:71B9-7210 READ 하는 PC (SJIS 렌더/복사 루틴)\n\n")
  table.sort(order, function(a, b) return agg[a].n > agg[b].n end)
  for _, pc in ipairs(order) do
    local e = agg[pc]
    f:write(string.format("PC=$%02X:%04X  n=%-5d  A=%04X X=%04X Y=%04X D=%04X DBR=%02X  read=$%04X..%04X (f%d)\n",
      pc >> 16, pc & 0xFFFF, e.n, e.a, e.x, e.y, e.d, e.dbr, e.minA & 0xFFFF, e.maxA & 0xFFFF, e.fr))
  end
  f:close()
end

emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  local on = (fr % 40) < 6            -- 주기적으로 스타트
  pressStart(on)
  if fr % 30 == 0 then pcall(dump) end
  if fr >= 900 and not done then done = true; pcall(dump); emu.stop(0) end
end, emu.eventType.endFrame)
