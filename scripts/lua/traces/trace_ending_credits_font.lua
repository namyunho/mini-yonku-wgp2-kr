-- trace_ending_credits_font.lua
--
-- 실제 최종 엔딩 크레딧의 글꼴 저장→해제→WRAM→VRAM 연결을 추적한다.
-- 조작이나 메모리 쓰기는 하지 않는다. 스크립트를 켠 채 엔딩에 진입하면
-- tmp/ending_credits_font_trace/LATEST.txt 아래 실행 폴더에 로그와 덤프가 생긴다.

local TRACE_ROOT =
  "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/ending_credits_font_trace/"
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

local function cpu_pc(st)
  return hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4)
end

local function read8(address)
  return emu.read(address, emu.memType.snesMemory) & 0xFF
end

local function read24(address)
  return read8(address) | (read8(address + 1) << 8) |
    (read8(address + 2) << 16)
end

local function address24(value)
  return hex((value >> 16) & 0xFF, 2) .. ":" .. hex(value & 0xFFFF, 4)
end

local function bytes_at(address, size)
  local out = {}
  for i = 0, size - 1 do
    out[#out + 1] = hex(read8(address + i), 2)
  end
  return table.concat(out, " ")
end

local function write_blob(path, first, size, mem_type)
  local file = assert(io.open(path, "wb"))
  local chunk = {}
  for i = 0, size - 1 do
    chunk[#chunk + 1] = string.char(
      emu.read(first + i, mem_type) & 0xFF
    )
    if #chunk == 4096 then
      file:write(table.concat(chunk))
      chunk = {}
    end
  end
  if #chunk > 0 then file:write(table.concat(chunk)) end
  file:close()
end

local function open_log(name, header)
  local file = assert(io.open(ROOT .. name, "w"))
  file:write(header .. "\n")
  file:flush()
  return file
end

local events = open_log("events.tsv", "frame\tkind\tpc\tdetail")
local wrappers = open_log(
  "lzss_wrappers.tsv",
  "frame\tpc\tcaller_inline\tsource\traw_size\tfirst16"
)
local decompressors = open_log(
  "lzss_calls.tsv",
  "frame\tpc\tdp\tsource\traw_size\tfirst16"
)
local dmas = open_log(
  "vram_dma.tsv",
  "seq\tframe\tpc\tchannel\tmode\tbbus\tsource\tsize\tvmadd\tfirst16"
)

local function event(kind, detail, st)
  st = st or state()
  events:write(table.concat({
    tostring(st["frameCount"] or 0), kind, cpu_pc(st), detail or "",
  }, "\t") .. "\n")
  events:flush()
end

local ending_active_until = -1
local pending_capture = nil
local capture_count = 0
local capture_limit = 24

local function mark_ending(kind)
  local st = state()
  ending_active_until = (st["frameCount"] or 0) + 1800
  pending_capture = kind
  event(kind, "", st)
end

-- C3의 세 공통 소형 글꼴 로더 후보. JSL $C3:53C7 뒤의 3바이트가
-- LZSS 소스 롱포인터다. 실제 엔딩에서 어느 후보가 실행되는지 기록한다.
local loader_candidates = {
  [0xC367A4] = "loader_C3_67A4",
  [0xC36B31] = "loader_C3_6B31",
  [0xC36CFF] = "loader_C3_6CFF",
  [0x8367A4] = "loader_83_67A4",
  [0x836B31] = "loader_83_6B31",
  [0x836CFF] = "loader_83_6CFF",
}
for address, label in pairs(loader_candidates) do
  emu.addMemoryCallback(function()
    local source = read24(address + 4)
    local raw_size = read8(source) | (read8(source + 1) << 8)
    event(
      label,
      "inline=" .. address24(address + 4) ..
      " source=" .. address24(source) ..
      " raw=" .. tostring(raw_size) ..
      " first16=" .. bytes_at(source, 16)
    )
    pending_capture = label
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- 실제 엔딩 초기화와 행 인터프리터. 이 이벤트 뒤 30초 동안 DMA를
-- 엔딩 소비 경로로 간주하고 체크포인트를 남긴다.
for address, label in pairs({
  [0xC38275] = "ending_init_C3_8275",
  [0x838275] = "ending_init_83_8275",
  [0xC38285] = "ending_rows_C3_8285",
  [0x838285] = "ending_rows_83_8285",
}) do
  emu.addMemoryCallback(function() mark_ending(label) end,
    emu.callbackType.exec, address, address,
    emu.cpuType.snes, emu.memType.snesMemory)
end

-- LZSS 래퍼 진입 시 스택의 long return address 바로 뒤 인라인 포인터를 읽는다.
local function trace_wrapper()
  local st = state()
  local sp = st["cpu.sp"] or st["cpu.s"] or 0
  local return_low = read8((sp + 1) & 0xFFFF)
  local return_high = read8((sp + 2) & 0xFFFF)
  local return_bank = read8((sp + 3) & 0xFFFF)
  local inline = (return_bank << 16) |
    ((((return_high << 8) | return_low) + 1) & 0xFFFF)
  local source = read24(inline)
  local raw_size = read8(source) | (read8(source + 1) << 8)
  wrappers:write(table.concat({
    tostring(st["frameCount"] or 0), cpu_pc(st), address24(inline),
    address24(source), tostring(raw_size), bytes_at(source, 16),
  }, "\t") .. "\n")
  wrappers:flush()
end
for _, address in ipairs({0xC353C7, 0x8353C7}) do
  emu.addMemoryCallback(trace_wrapper, emu.callbackType.exec,
    address, address, emu.cpuType.snes, emu.memType.snesMemory)
end

-- LZSS 본체의 DP $11-$13 소스가 실제로 어느 자원을 받았는지 기록한다.
local function trace_decompressor()
  local st = state()
  local direct = st["cpu.d"] or 0
  local source = read8(direct + 0x11) |
    (read8(direct + 0x12) << 8) |
    (read8(direct + 0x13) << 16)
  local raw_size = read8(source) | (read8(source + 1) << 8)
  decompressors:write(table.concat({
    tostring(st["frameCount"] or 0), cpu_pc(st), hex(direct, 4),
    address24(source), tostring(raw_size), bytes_at(source, 16),
  }, "\t") .. "\n")
  decompressors:flush()
end
for _, address in ipairs({0xC00D52, 0x800D52, 0xC00D91, 0x800D91}) do
  emu.addMemoryCallback(trace_decompressor, emu.callbackType.exec,
    address, address, emu.cpuType.snes, emu.memType.snesMemory)
end

local dma_seq = 0
emu.addMemoryCallback(function(_, mask)
  local st = state()
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local prefix = "dmaController.channel[" .. channel .. "]."
      local bbus = st[prefix .. "destAddress"] or 0
      if bbus == 0x18 or bbus == 0x19 then
        dma_seq = dma_seq + 1
        local source_bank = st[prefix .. "srcBank"] or 0
        local source_offset = st[prefix .. "srcAddress"] or 0
        local source = (source_bank << 16) | source_offset
        local size = st[prefix .. "transferSize"] or 0
        if size == 0 then size = 65536 end
        local vmadd = st["ppu.vramAddress"] or 0
        dmas:write(table.concat({
          tostring(dma_seq), tostring(st["frameCount"] or 0), cpu_pc(st),
          tostring(channel), tostring(st[prefix .. "transferMode"] or 0),
          hex(bbus, 2), address24(source), tostring(size), hex(vmadd, 4),
          bytes_at(source, math.min(size, 16)),
        }, "\t") .. "\n")
        dmas:flush()
        if (st["frameCount"] or 0) <= ending_active_until or
           size == 0x1000 then
          pending_capture = "dma_" .. hex(vmadd, 4) ..
            "_" .. tostring(size) .. "_" .. tostring(dma_seq)
        end
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
  emu.cpuType.snes, emu.memType.snesMemory)

local function capture(reason)
  if capture_count >= capture_limit then return end
  capture_count = capture_count + 1
  local st = state()
  local frame = st["frameCount"] or 0
  local stem = string.format(
    "%02d_f%07d_%s", capture_count, frame, reason
  )
  write_blob(
    ROOT .. stem .. "_vram.bin", 0, 0x10000,
    emu.memType.snesVideoRam
  )
  write_blob(
    ROOT .. stem .. "_wram.bin", 0x7E0000, 0x20000,
    emu.memType.snesMemory
  )
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local file = assert(io.open(ROOT .. stem .. "_screen.png", "wb"))
    file:write(png)
    file:close()
  end
  event("capture", stem, st)
  emu.displayMessage(
    "ending font trace",
    "dump " .. tostring(capture_count) .. ": " .. reason
  )
end

emu.addEventCallback(function()
  if pending_capture then
    local reason = pending_capture
    pending_capture = nil
    capture(reason)
  end
end, emu.eventType.endFrame)

capture("script_start")
event(
  "live_rom_probe",
  "C3:6D03=" .. bytes_at(0xC36D03, 3) ..
  " C3:67A8=" .. bytes_at(0xC367A8, 3) ..
  " C3:6B35=" .. bytes_at(0xC36B35, 3) ..
  " D9:E000=" .. bytes_at(0xD9E000, 16) ..
  " D9:0000=" .. bytes_at(0xD90000, 16)
)
event("ready", "enter final ending credits")
emu.displayMessage("ending font trace", "ready - enter final credits")
