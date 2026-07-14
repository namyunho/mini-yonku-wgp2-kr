-- trace_decomp.lua : 오프닝 그래픽 디컴프레서 규명.
--   출력버퍼 $7F:1000~ 에 쓰는 PC를 집계 + 초반 쓰기의 레지스터/DP 롱포인터 캡처
--   → 압축 소스(ROM) 주소·코덱 역추적. 디컴프는 부팅 직후(~f67) 발생.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local WLO, WHI = 0x7F1000, 0x7F13FF     -- 출력버퍼 앞부분(SNES 주소)

local agg = {}      -- pc -> {n, dbr, minA, maxA}
local order = {}
local timeline = {} -- 초반 쓰기 상세

local function onWrite(addr, value)
  local st = emu.getState()
  local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
  local e = agg[pc]
  if not e then e = { n = 0, dbr = st["cpu.dbr"], minA = addr, maxA = addr, fr = st["frameCount"] }; agg[pc] = e; order[#order+1] = pc end
  e.n = e.n + 1
  if addr < e.minA then e.minA = addr end
  if addr > e.maxA then e.maxA = addr end
  if #timeline < 48 then
    local d = st["cpu.d"]
    -- DP 부근 롱포인터 후보들 덤프 ($00..$1F)
    local dp = {}
    for i = 0, 0x1F do dp[i] = emu.read(d + i, emu.memType.snesWorkRam) end
    timeline[#timeline+1] = string.format(
      "PC=$%02X:%04X a=%04X x=%04X y=%04X D=%04X DBR=%02X -> $%06X=%02X | DP00-0F=%s",
      pc>>16, pc&0xFFFF, st["cpu.a"], st["cpu.x"], st["cpu.y"], d, st["cpu.dbr"], addr, value,
      table.concat((function() local t={} for i=0,15 do t[#t+1]=string.format("%02X",dp[i]) end return t end)(), " "))
  end
end
emu.addMemoryCallback(onWrite, emu.callbackType.write, WLO, WHI, emu.cpuType.snes, emu.memType.snesMemory)

local done = false
local function dump()
  local f = io.open(ROOT .. "decomp.txt", "w")
  if not f then return end
  f:write("# $7F:1000-13FF 에 쓰는 PC (디컴프레서 store)\n")
  table.sort(order, function(a,b) return agg[a].n > agg[b].n end)
  for _, pc in ipairs(order) do
    local e = agg[pc]
    f:write(string.format("PC=$%02X:%04X n=%-6d DBR=%02X dst=$%04X..%04X (f%d)\n",
      pc>>16, pc&0xFFFF, e.n, e.dbr, e.minA&0xFFFF, e.maxA&0xFFFF, e.fr))
  end
  f:write("\n# 초반 48 쓰기 상세(레지스터·DP)\n")
  for _, s in ipairs(timeline) do f:write(s .. "\n") end
  f:close()
end

emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  if fr == 80 and not done then done = true; pcall(dump); emu.stop(0) end
end, emu.eventType.endFrame)
