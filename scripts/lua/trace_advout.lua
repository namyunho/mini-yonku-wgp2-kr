-- trace_advout.lua : 어드벤처 엔진의 디코드 출력(글리프 스트림)과 소스 바이트를 함께 캡처.
--   $C0:3A4D STA [$15],Y = 디코드 결과 1바이트 출력.  $C0:39E7 LDA [$11] = 소스 1바이트 입력.
--   → 입력(소스)·출력(디코드 글리프) 쌍을 순서대로 로그 → 오프라인 코덱 역공학·검증.
--   사용법: 원본 ROM → 어드벤처 대화 1~2장면.  산출: tmp/trace/adv_io.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"

local outseq = {}   -- 출력 바이트 순서열 (글리프 스트림)
local inseq = {}    -- 소스 바이트 순서열 (+주소)
local MAX = 8000

local function onOut()
  if #outseq >= MAX then return end
  local st = emu.getState()
  outseq[#outseq + 1] = st["cpu.a"] & 0xFF
end

local function onIn()
  if #inseq >= MAX then return end
  local st = emu.getState()
  local d = st["cpu.d"] or 0
  local lo = emu.read(d + 0x11, emu.memType.snesMemory)
  local hi = emu.read(d + 0x12, emu.memType.snesMemory)
  local bk = emu.read(d + 0x13, emu.memType.snesMemory)
  -- 읽히는 소스 바이트 값
  local val = emu.read((bk << 16) | (hi << 8) | lo, emu.memType.snesMemory)
  inseq[#inseq + 1] = string.format("%02X:%04X=%02X", bk, hi * 0x100 + lo, val)
end

emu.addMemoryCallback(onOut, emu.callbackType.exec, 0xC03A4D, 0xC03A4D,
  emu.cpuType.snes, emu.memType.snesMemory)
emu.addMemoryCallback(onIn, emu.callbackType.exec, 0xC039E7, 0xC039E7,
  emu.cpuType.snes, emu.memType.snesMemory)

local function dump()
  local f = io.open(ROOT .. "adv_io.txt", "w")
  if not f then return end
  f:write(string.format("# frame=%d out=%d in=%d\n\n", emu.getState()["frameCount"], #outseq, #inseq))
  f:write("## OUT (decoded glyph bytes, in write order) ##\n")
  local line = {}
  for i, v in ipairs(outseq) do
    line[#line + 1] = string.format("%02X", v)
    if #line == 32 then f:write(table.concat(line, " ") .. "\n"); line = {} end
  end
  if #line > 0 then f:write(table.concat(line, " ") .. "\n") end
  f:write("\n## IN (source bytes read via [$11]) ##\n")
  for i, s in ipairs(inseq) do
    f:write(s .. "  ")
    if i % 8 == 0 then f:write("\n") end
  end
  f:close()
end

local fc = 0
emu.addEventCallback(function()
  fc = fc + 1
  if fc % 60 == 0 then pcall(dump) end
end, emu.eventType.endFrame)
