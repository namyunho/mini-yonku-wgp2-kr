-- render_trace.lua : 레이스 대사가 그려질 때 WRAM 라인버퍼($7E:A000~$7E:AC00) 쓰기를 후킹.
-- 각 쓰기의 PC·레지스터를 PC별로 집계 → 글리프 블리터 루틴과 그 폰트 소스(X/DBR/DP)를 규명.
--   글리프 소스 뱅크가 ROM($Cx)이면 폰트가 ROM 비압축 → 정적 재조준
--   글리프 소스 뱅크가 WRAM($7E/$7F)이면 폰트가 디컴프됨 → 디컴프레서 추적
-- 산출: tmp/trace/render_trace.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local LO, HI = 0xA000, 0xAC00          -- WRAM 선형 오프셋 감시창
local GATE_FROM, GATE_TO = 1040, 1210  -- 대사 그리는 구간만
local MAXROWS = 6000

local agg = {}     -- pc -> {n, a,x,y,d,dbr, minAddr, maxAddr, firstFrame}
local rows = 0
local logAll = {}  -- 초반 시계열 샘플

local function onWrite(addr, value)
  local st = emu.getState()
  local fr = st["frameCount"]
  if fr < GATE_FROM or fr > GATE_TO then return end
  rows = rows + 1
  if rows > MAXROWS then return end
  local k = st["cpu.k"]; local pc = st["cpu.pc"]
  local key = k * 0x10000 + pc
  local e = agg[key]
  if not e then
    e = { n = 0, a = st["cpu.a"], x = st["cpu.x"], y = st["cpu.y"],
          d = st["cpu.d"], dbr = st["cpu.dbr"], minA = addr, maxA = addr, ff = fr }
    agg[key] = e
  end
  e.n = e.n + 1
  if addr < e.minA then e.minA = addr end
  if addr > e.maxA then e.maxA = addr end
  if #logAll < 60 then
    logAll[#logAll + 1] = string.format(
      "f=%d PC=$%02X:%04X addr=$7E:%04X val=$%02X A=%04X X=%04X Y=%04X D=%04X DBR=%02X",
      fr, k, pc, addr, value, st["cpu.a"], st["cpu.x"], st["cpu.y"], st["cpu.d"], st["cpu.dbr"])
  end
end

emu.addMemoryCallback(onWrite, emu.callbackType.write, LO, HI, emu.cpuType.snes, emu.memType.snesWorkRam)

local done = false
local function onFrame()
  local fr = emu.getState()["frameCount"]
  local on = (fr >= 200 and fr < 208) or (fr >= 400 and fr < 408) or (fr >= 600 and fr < 608)
  pcall(function() emu.setInput(1, { start = on }) end)
  if fr >= GATE_TO and not done then
    done = true
    local f = io.open(ROOT .. "render_trace.txt", "w")
    f:write(string.format("window $7E:%04X-%04X  gate f%d-%d  total writes(capped)=%d\n\n",
      LO, HI, GATE_FROM, GATE_TO, rows))
    -- PC별 집계 정렬(빈도순)
    local list = {}
    for key, e in pairs(agg) do list[#list + 1] = { key = key, e = e } end
    table.sort(list, function(a, b) return a.e.n > b.e.n end)
    f:write("=== writers by PC (freq desc) ===\n")
    for _, it in ipairs(list) do
      local e = it.e
      f:write(string.format(
        "PC=$%02X:%04X  n=%-5d dstRange=$%04X-$%04X  sampleRegs A=%04X X=%04X Y=%04X D=%04X DBR=%02X (f%d)\n",
        it.key >> 16, it.key & 0xFFFF, e.n, e.minA, e.maxA, e.a, e.x, e.y, e.d, e.dbr, e.ff))
    end
    f:write("\n=== first 60 writes (timeline) ===\n")
    for _, s in ipairs(logAll) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end
emu.addEventCallback(onFrame, emu.eventType.endFrame)
