-- trace_advptr.lua : 어드벤처 텍스트 엔진의 소스 포인터 [$11]($11-$13) 포착.
--   엔진 $C0:39E0~ 은 LDA [$11] 로 소스 텍스트를 1바이트씩 읽고 $11(:$13 뱅크)을 증가시킨다.
--   $C0:3A05(LDA [$11]) 실행마다 $13:$12:$11 = 읽는 소스 주소 → 뱅크·범위 확정.
--   사용법: 원본 ROM → 어드벤처 대화 장면들 지나가기.  산출: tmp/trace/adv_ptr.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"

local seen = {}       -- 24bit src addr -> true
local nseen = 0
local hits = 0
local bmin, bmax, bcnt = {}, {}, {}

local function onExec()
  hits = hits + 1
  local st = emu.getState()
  local d = st["cpu.d"] or 0
  local lo = emu.read(d + 0x11, emu.memType.snesMemory)
  local hi = emu.read(d + 0x12, emu.memType.snesMemory)
  local bk = emu.read(d + 0x13, emu.memType.snesMemory)
  local addr = hi * 0x100 + lo
  local key = bk * 0x10000 + addr
  if not seen[key] then
    seen[key] = true; nseen = nseen + 1
    if bmin[bk] == nil or addr < bmin[bk] then bmin[bk] = addr end
    if bmax[bk] == nil or addr > bmax[bk] then bmax[bk] = addr end
    bcnt[bk] = (bcnt[bk] or 0) + 1
  end
end

-- 엔진의 소스 읽기 지점들 (LDA [$11])
emu.addMemoryCallback(onExec, emu.callbackType.exec, 0xC03A05, 0xC03A05,
  emu.cpuType.snes, emu.memType.snesMemory)
emu.addMemoryCallback(onExec, emu.callbackType.exec, 0xC03A1B, 0xC03A1B,
  emu.cpuType.snes, emu.memType.snesMemory)

local function dump()
  local f = io.open(ROOT .. "adv_ptr.txt", "w")
  if not f then return end
  f:write(string.format("# frame=%d hits=%d distinct_src=%d\n\n",
    emu.getState()["frameCount"], hits, nseen))
  f:write("## 소스 텍스트 뱅크별 스팬 ##\n")
  local bl = {}
  for b, _ in pairs(bcnt) do bl[#bl + 1] = b end
  table.sort(bl)
  for _, b in ipairs(bl) do
    f:write(string.format("BANK $%02X : n=%-5d  $%04X..$%04X\n", b, bcnt[b], bmin[b], bmax[b]))
  end
  f:write("\n## 읽힌 소스 주소 ##\n")
  local al = {}
  for k, _ in pairs(seen) do al[#al + 1] = k end
  table.sort(al)
  for _, k in ipairs(al) do
    f:write(string.format("%02X:%04X\n", k // 0x10000, k % 0x10000))
  end
  f:close()
end

local fc = 0
emu.addEventCallback(function()
  fc = fc + 1
  if fc % 60 == 0 then pcall(dump) end
end, emu.eventType.endFrame)
