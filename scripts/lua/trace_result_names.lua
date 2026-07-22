-- trace_result_names.lua
--
-- 경기 종료 Result 화면의 선수명 경로를 한 번의 수동 진입으로 추적한다.
-- 사용자는 이 스크립트를 켠 채 경기 종료 화면으로 이동하기만 하면 된다.
--
-- 기록 대상:
--   * $D9:0000 공통 소형 폰트 해제 및 정적 로더 후보 3곳
--   * 모든 VRAM DMA와 WRAM 소스의 실행 직전 사본
--   * $C0:F410 레이서 포인터/문자열 표 접근
--   * $C1:D1C3 표준 SJIS 변환표 접근
--   * $7F:1000의 $D9 해제 폰트 버퍼를 읽는 CPU 호출자
--   * 표준 SJIS 렌더러와 직접 타일 렌더러 진입
--   * DMA가 있었던 프레임의 VRAM/WRAM/PPU/스크린샷 체크포인트

local TRACE_ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/result_trace/"
local RUN_ID = os.date("%Y%m%d_%H%M%S")
local ROOT = TRACE_ROOT .. "run_" .. RUN_ID .. "/"
os.execute('mkdir -p "' .. ROOT .. '"')

local latest = assert(io.open(TRACE_ROOT .. "LATEST.txt", "w"))
latest:write(ROOT .. "\n")
latest:close()

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function state()
  return emu.getState()
end

local function frame()
  return state()["frameCount"] or 0
end

local function cpu_pc(st)
  return hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4)
end

local function read8(address)
  return emu.read(address, emu.memType.snesMemory) & 0xFF
end

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local chunk = {}
  for i = 0, size - 1 do
    chunk[#chunk + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
    if #chunk == 4096 then
      f:write(table.concat(chunk))
      chunk = {}
    end
  end
  if #chunk > 0 then f:write(table.concat(chunk)) end
  f:close()
end

local function open_log(name, header)
  local f = assert(io.open(ROOT .. name, "w"))
  f:write(header .. "\n")
  f:flush()
  return f
end

local events = open_log("events.tsv", "frame\tkind\tpc\tdetail")
local dma_log = open_log(
  "vram_dma.tsv",
  "seq\tframe\tpc\tchannel\tmode\tbbus\tsource\tsize\tvmadd\ttile2bpp\ttile4bpp\tfixed\tdecrement\tinvert"
)
local renderer_log = open_log(
  "renderer_calls.tsv",
  "frame\trenderer\tpc\ta\tx\ty\td\tsp\tstack16"
)
local name_read_log = open_log(
  "name_table_reads.tsv",
  "frame\tpc\taddress\tvalue"
)
local sjis_read_log = open_log(
  "sjis_table_reads.tsv",
  "frame\tpc\taddress\tvalue"
)
local font_read_log = open_log(
  "d9_buffer_reads.tsv",
  "frame\tpc\taddress\tvalue"
)
local port_log = open_log(
  "vram_port_writes.tsv",
  "frame\tpc\tregister\tvalue\tvmadd"
)

local function event(kind, detail, st)
  st = st or state()
  events:write(table.concat({
    tostring(st["frameCount"] or 0), kind, cpu_pc(st), detail or ""
  }, "\t") .. "\n")
  events:flush()
end

local armed = true
local dirty_vram = true
local pending_reason = "script_start"
local checkpoint_count = 0
local checkpoint_limit = 64
local last_checkpoint_frame = -1
local dma_seq = 0
local name_read_count = 0
local sjis_read_count = 0
local font_read_count = 0
local port_write_count = 0

local function stack_sample(st)
  local sp = st["cpu.sp"] or st["cpu.s"] or 0
  local out = {}
  for i = 1, 16 do out[#out + 1] = hex(read8((sp + i) & 0xFFFF), 2) end
  return table.concat(out, " "), sp
end

local function sorted_state(st)
  local keys = {}
  for key, _ in pairs(st) do keys[#keys + 1] = key end
  table.sort(keys)
  local out = {}
  for _, key in ipairs(keys) do
    out[#out + 1] = string.format("%s=%s", key, tostring(st[key]))
  end
  return table.concat(out, "\n") .. "\n"
end

local function checkpoint(reason)
  if checkpoint_count >= checkpoint_limit then return end
  local st = state()
  local fr = st["frameCount"] or 0
  if fr == last_checkpoint_frame then return end
  last_checkpoint_frame = fr
  checkpoint_count = checkpoint_count + 1
  local stem = string.format("%02d_f%07d_%s", checkpoint_count, fr, reason)

  local sf = assert(io.open(ROOT .. stem .. "_state.txt", "w"))
  sf:write(sorted_state(st))
  sf:close()
  write_blob(ROOT .. stem .. "_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(ROOT .. stem .. "_wram.bin", 0x7E0000, 0x20000, emu.memType.snesMemory)

  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local pf = assert(io.open(ROOT .. stem .. "_screen.png", "wb"))
    pf:write(png)
    pf:close()
  end
  event("checkpoint", stem, st)
  emu.displayMessage("result trace", string.format("dump %02d: %s", checkpoint_count, reason))
end

local function arm(reason)
  armed = true
  dirty_vram = true
  pending_reason = reason
  event("arm", reason)
end

-- $D9:0000을 인라인 포인터로 넘기는 정적 로더 후보.
-- C3 뱅크와 HiROM 미러 83 뱅크를 함께 감시한다.
local loader_candidates = {
  [0xC367A4] = "d9_loader_C3_67A4",
  [0xC36B31] = "d9_loader_C3_6B31",
  [0xC36CFF] = "d9_loader_C3_6CFF",
  [0x8367A4] = "d9_loader_83_67A4",
  [0x836B31] = "d9_loader_83_6B31",
  [0x836CFF] = "d9_loader_83_6CFF",
}
for address, label in pairs(loader_candidates) do
  emu.addMemoryCallback(function()
    arm(label)
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- $C3:69B9의 화면 상태 디스패치 표. 정적 분석상 Result 초기화/대기/종료
-- 경로 후보이며, 실제 진입 순서를 기록해 로더와 이름 갱신 프레임을 묶는다.
local result_states = {
  [0xC3667A] = "result_state_0_C3_667A",
  [0xC3668D] = "result_state_1_C3_668D",
  [0xC3690E] = "result_state_2_C3_690E",
  [0xC3696B] = "result_state_3_C3_696B",
  [0xC36921] = "result_state_4_C3_6921",
  [0xC3693B] = "result_state_5_C3_693B",
}
for address, label in pairs(result_states) do
  emu.addMemoryCallback(function()
    local st = state()
    event(label, table.concat({
      "state=" .. hex(read8(0x0084) | (read8(0x0085) << 8), 4),
      "counter133A=" .. hex(read8(0x133A) | (read8(0x133B) << 8), 4),
      "counter1340=" .. hex(read8(0x1340) | (read8(0x1341) << 8), 4),
      "flag1376=" .. hex(read8(0x1376), 2),
    }, " "), st)
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- LZSS 본체 진입. DP $11-$13이 $D9:0000이면 Result를 포함한 공통 폰트 로드다.
local function trace_decompress()
  local st = state()
  local d = st["cpu.d"] or 0
  local src_addr = read8(d + 0x11) | (read8(d + 0x12) << 8)
  local src_bank = read8(d + 0x13)
  if src_bank == 0xD9 and (src_addr == 0x0000 or src_addr == 0x0002) then
    arm("d9_decompress_" .. hex(src_addr, 4))
  end
end
for _, address in ipairs({0xC00D91, 0x800D91}) do
  emu.addMemoryCallback(trace_decompress, emu.callbackType.exec,
      address, address, emu.cpuType.snes, emu.memType.snesMemory)
end

local function trace_renderer(label)
  if not armed then return end
  local st = state()
  local sample, sp = stack_sample(st)
  renderer_log:write(table.concat({
    tostring(st["frameCount"] or 0), label, cpu_pc(st),
    hex(st["cpu.a"], 4), hex(st["cpu.x"], 4), hex(st["cpu.y"], 4),
    hex(st["cpu.d"], 4), hex(sp, 4), sample,
  }, "\t") .. "\n")
  renderer_log:flush()
end
for _, address in ipairs({0xC1965E, 0x81965E}) do
  emu.addMemoryCallback(function() trace_renderer("sjis_C1_965E") end,
      emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end
for _, address in ipairs({0xC01B4B, 0x801B4B}) do
  emu.addMemoryCallback(function() trace_renderer("direct_C0_1B4B") end,
      emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

local function trace_read(log, kind, cap)
  return function(address, value)
    if not armed then return end
    if kind == "name" then
      if name_read_count >= cap then return end
      name_read_count = name_read_count + 1
    elseif kind == "sjis" then
      if sjis_read_count >= cap then return end
      sjis_read_count = sjis_read_count + 1
    else
      if font_read_count >= cap then return end
      font_read_count = font_read_count + 1
    end
    local st = state()
    log:write(table.concat({
      tostring(st["frameCount"] or 0), cpu_pc(st), hex(address, 6), hex(value, 2)
    }, "\t") .. "\n")
    if ((name_read_count + sjis_read_count + font_read_count) & 0x3F) == 0 then
      log:flush()
    end
  end
end

-- 원본 레이서 ID 포인터표 $C0:F410-$F4B9 + 문자열 $F4BA-$F717.
for _, bank_base in ipairs({0xC00000, 0x800000}) do
  emu.addMemoryCallback(trace_read(name_read_log, "name", 20000),
      emu.callbackType.read, bank_base + 0xF410, bank_base + 0xF717,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- 표준 SJIS 변환표. Result 선수명이 이 경로라면 읽기가 반드시 나타난다.
for _, bank_base in ipairs({0xC10000, 0x810000}) do
  emu.addMemoryCallback(trace_read(sjis_read_log, "sjis", 20000),
      emu.callbackType.read, bank_base + 0xD1C3, bank_base + 0xD7FF,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- $D9:0002 해제 결과 5984B = $7F:1000-$275F. CPU가 글리프를 복사한다면
-- 이 콜백의 PC가 Result 전용 이름 렌더러다. DMA 읽기는 별도 vram_dma.tsv에 남는다.
emu.addMemoryCallback(trace_read(font_read_log, "font", 50000),
    emu.callbackType.read, 0x7F1000, 0x7F275F,
    emu.cpuType.snes, emu.memType.snesMemory)

local function dump_dma_source(seq, bank, address, size)
  if bank ~= 0x7E and bank ~= 0x7F then return end
  if size <= 0 or size > 0x4000 then return end
  local path = ROOT .. string.format(
    "dma_%04d_f%07d_src_%02X_%04X_%d.bin", seq, frame(), bank, address, size)
  write_blob(path, (bank << 16) | address, size, emu.memType.snesMemory)
end

emu.addMemoryCallback(function(_, mask)
  if not armed then return end
  local st = state()
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local p = "dmaController.channel[" .. channel .. "]."
      local bbus = st[p .. "destAddress"] or 0
      if bbus == 0x18 or bbus == 0x19 then
        dma_seq = dma_seq + 1
        local source_bank = st[p .. "srcBank"] or 0
        local source_addr = st[p .. "srcAddress"] or 0
        local size = st[p .. "transferSize"] or 0
        if size == 0 then size = 65536 end
        local vmadd = st["ppu.vramAddress"] or 0
        dma_log:write(table.concat({
          tostring(dma_seq), tostring(st["frameCount"] or 0), cpu_pc(st),
          tostring(channel), hex(st[p .. "transferMode"], 2), hex(bbus, 2),
          hex(source_bank, 2) .. ":" .. hex(source_addr, 4), tostring(size),
          hex(vmadd, 4), tostring(vmadd // 8), tostring(vmadd // 16),
          tostring(st[p .. "fixedTransfer"] or false),
          tostring(st[p .. "decrementTransfer"] or false),
          tostring(st[p .. "invertDirection"] or false),
        }, "\t") .. "\n")
        dma_log:flush()
        dump_dma_source(dma_seq, source_bank, source_addr, size)
        dirty_vram = true
        pending_reason = string.format("vram_dma_%04d", dma_seq)
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
    emu.cpuType.snes, emu.memType.snesMemory)

-- DMA가 아닌 직접 VRAM 포트 쓰기도 놓치지 않는다.
emu.addMemoryCallback(function(address, value)
  if not armed or port_write_count >= 5000 then return end
  port_write_count = port_write_count + 1
  local st = state()
  port_log:write(table.concat({
    tostring(st["frameCount"] or 0), cpu_pc(st), hex(address, 4),
    hex(value, 2), hex(st["ppu.vramAddress"], 4),
  }, "\t") .. "\n")
  if (port_write_count & 0x3F) == 0 then port_log:flush() end
  dirty_vram = true
  pending_reason = "direct_vram"
end, emu.callbackType.write, 0x2118, 0x2119,
    emu.cpuType.snes, emu.memType.snesMemory)

local ticks = 0
emu.addEventCallback(function()
  ticks = ticks + 1
  if dirty_vram then
    dirty_vram = false
    checkpoint(pending_reason or "vram_change")
    pending_reason = nil
  elseif ticks % 120 == 0 then
    checkpoint("periodic")
  end
  if ticks == 1 then
    emu.displayMessage("result trace", "준비 완료: 경기 종료 Result 화면으로 이동하세요")
  end
end, emu.eventType.endFrame)

local info = assert(io.open(ROOT .. "run_info.txt", "w"))
info:write("run_id=" .. RUN_ID .. "\n")
info:write("trace_root=" .. ROOT .. "\n")
info:write("instruction=Keep this script active and enter a post-race Result screen.\n")
info:close()

event("script_start", ROOT)
