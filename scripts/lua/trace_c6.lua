-- trace_c6.lua : 어드벤처 텍스트 엔진 규명.
--   뱅크 $C6(대사 조각 풀 추정) 데이터 READ를 후킹 → 읽는 명령의 PC와 주소범위 수집.
--   → 어드벤처 대사를 화면에 띄우는 '텍스트 리더' 루프의 위치(엔진)와 실제 읽는 텍스트 스팬 확정.
--   사용법: 원본 ROM 실행 → 어드벤처 대화(박사·동료 등) 한두 장면 지나가기.
--   산출(1초마다): tmp/trace/c6_read.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"

local pcs = {}       -- pc(k:addr) -> {count, amin, amax}
local addrs = {}     -- 읽힌 $C6 주소 set
local naddr = 0
local reads = 0

local function onRead(addr, value)
  reads = reads + 1
  local a = addr & 0xFFFF          -- $C6:xxxx
  if not addrs[a] then addrs[a] = true; naddr = naddr + 1 end
  local st = emu.getState()
  local pc = (st["cpu.k"] << 16) | st["cpu.pc"]
  local e = pcs[pc]
  if e == nil then pcs[pc] = { 1, a, a }
  else e[1] = e[1] + 1; if a < e[2] then e[2] = a end; if a > e[3] then e[3] = a end end
end

emu.addMemoryCallback(onRead, emu.callbackType.read, 0xC60000, 0xC6FFFF,
  emu.cpuType.snes, emu.memType.snesMemory)

local function dump()
  local f = io.open(ROOT .. "c6_read.txt", "w")
  if not f then return end
  f:write(string.format("# frame=%d $C6_reads=%d distinct_addrs=%d\n\n",
    emu.getState()["frameCount"], reads, naddr))
  -- 읽는 명령 PC (빈도순): 텍스트 리더 루프 후보
  f:write("## $C6를 읽는 명령 PC (count, addr범위) ##\n")
  local arr = {}
  for pc, e in pairs(pcs) do arr[#arr + 1] = { pc, e[1], e[2], e[3] } end
  table.sort(arr, function(a, b) return a[2] > b[2] end)
  for i = 1, math.min(#arr, 30) do
    local x = arr[i]
    f:write(string.format("pc $%06X  x%-6d  $%04X..$%04X\n", x[1], x[2], x[3], x[4]))
  end
  -- 읽힌 주소 목록
  f:write("\n## 읽힌 $C6 주소 (정렬) ##\n")
  local al = {}
  for a, _ in pairs(addrs) do al[#al + 1] = a end
  table.sort(al)
  for _, a in ipairs(al) do f:write(string.format("C6:%04X\n", a)) end
  f:close()
end

local fc = 0
emu.addEventCallback(function()
  fc = fc + 1
  if fc % 60 == 0 then pcall(dump) end
end, emu.eventType.endFrame)
