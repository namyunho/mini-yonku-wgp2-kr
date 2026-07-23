-- trace_ending_logo.lua
--
-- 엔딩 VICTORYS 장면 하단의 일본어 WGP2 로고 소스를 찾는다.
-- 사용법:
--   1) 이 스크립트를 Mesen2에서 로드한다.
--   2) 스크립트를 켠 채 목표 엔딩 화면에 다시 진입한다.
--   3) 화면이 뜬 뒤 1~2초 기다린다.
--
-- 조작은 전혀 주입하지 않는다. 다음을 한 실행 폴더에 기록한다.
--   * LZSS 래퍼 $C3:53C7의 인라인 ROM 소스 포인터
--   * LZSS 본체 $C0:0D52/$C0:0D91의 DP $11-$13 소스
--   * 모든 VRAM DMA, 특히 word $0000 타일셋 / $7000 타일맵
--   * 직접 VRAM 포트 기록($2118/$2119)
--   * 목표 BG1 상태의 VRAM/WRAM/CGRAM/OAM/스크린샷
--
-- 산출:
--   tmp/ending_logo_trace/LATEST.txt
--   tmp/ending_logo_trace/run_YYYYMMDD_HHMMSS/

local TRACE_ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/ending_logo_trace/"
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

local function read_long(address)
  return read8(address) | (read8(address + 1) << 8) | (read8(address + 2) << 16)
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
local wrappers = open_log(
  "lzss_wrappers.tsv",
  "frame\tpc\tcaller\tinline_source\traw_size\tfirst16"
)
local decompressors = open_log(
  "lzss_calls.tsv",
  "frame\tentry\tpc\tdp\tsource\traw_size\tfirst16"
)
local dma = open_log(
  "vram_dma.tsv",
  "seq\tframe\tpc\tchannel\tmode\tbbus\tsource\tsize\tvmadd\tfixed\tdecrement\tinvert"
)
local ports = open_log(
  "vram_port_writes.tsv",
  "seq\tframe\tpc\tregister\tvalue\tvmadd"
)

local function event(kind, detail, st)
  st = st or state()
  events:write(table.concat({
    tostring(st["frameCount"] or 0), kind, cpu_pc(st), detail or ""
  }, "\t") .. "\n")
  events:flush()
end

local function bytes16(address)
  local out = {}
  for i = 0, 15 do out[#out + 1] = hex(read8(address + i), 2) end
  return table.concat(out, " ")
end

local function source_desc(address)
  return hex((address >> 16) & 0xFF, 2) .. ":" .. hex(address & 0xFFFF, 4)
end

-- $C3:53C7은 JSL 직후 3바이트 소스 롱포인터를 읽는 래퍼다.
local function trace_wrapper()
  local st = state()
  local sp = st["cpu.sp"] or st["cpu.s"] or 0
  local ret_lo = read8((sp + 1) & 0xFFFF)
  local ret_hi = read8((sp + 2) & 0xFFFF)
  local ret_bank = read8((sp + 3) & 0xFFFF)
  local return_address = (ret_bank << 16) | ((((ret_hi << 8) | ret_lo) + 1) & 0xFFFF)
  local source = read_long(return_address)
  local raw_size = read8(source) | (read8(source + 1) << 8)
  wrappers:write(table.concat({
    tostring(st["frameCount"] or 0), cpu_pc(st), source_desc(return_address),
    source_desc(source), tostring(raw_size), bytes16(source),
  }, "\t") .. "\n")
  wrappers:flush()
  event("lzss_wrapper", "source=" .. source_desc(source) .. " raw=" .. tostring(raw_size), st)
end

for _, address in ipairs({0xC353C7, 0x8353C7}) do
  emu.addMemoryCallback(trace_wrapper, emu.callbackType.exec,
    address, address, emu.cpuType.snes, emu.memType.snesMemory)
end

local function trace_decompressor(label)
  local st = state()
  local d = st["cpu.d"] or 0
  local source = read8(d + 0x11) | (read8(d + 0x12) << 8) | (read8(d + 0x13) << 16)
  local raw_size = read8(source) | (read8(source + 1) << 8)
  decompressors:write(table.concat({
    tostring(st["frameCount"] or 0), label, cpu_pc(st), hex(d, 4),
    source_desc(source), tostring(raw_size), bytes16(source),
  }, "\t") .. "\n")
  decompressors:flush()
end

for _, item in ipairs({
  {0xC00D52, "C0:0D52"}, {0x800D52, "80:0D52"},
  {0xC00D91, "C0:0D91"}, {0x800D91, "80:0D91"},
}) do
  local address, label = item[1], item[2]
  emu.addMemoryCallback(function() trace_decompressor(label) end,
    emu.callbackType.exec, address, address,
    emu.cpuType.snes, emu.memType.snesMemory)
end

local pending_capture = nil
local dma_seq = 0
emu.addMemoryCallback(function(_, mask)
  local st = state()
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local p = "dmaController.channel[" .. channel .. "]."
      local bbus = st[p .. "destAddress"] or 0
      if bbus == 0x18 or bbus == 0x19 then
        dma_seq = dma_seq + 1
        local vmadd = st["ppu.vramAddress"] or 0
        local src_bank = st[p .. "srcBank"] or 0
        local src_address = st[p .. "srcAddress"] or 0
        local size = st[p .. "transferSize"] or 0
        if size == 0 then size = 65536 end
        dma:write(table.concat({
          tostring(dma_seq), tostring(st["frameCount"] or 0), cpu_pc(st),
          tostring(channel), tostring(st[p .. "transferMode"] or 0), hex(bbus, 2),
          hex(src_bank, 2) .. ":" .. hex(src_address, 4), tostring(size), hex(vmadd, 4),
          tostring(st[p .. "fixedTransfer"] or false),
          tostring(st[p .. "decrement"] or false),
          tostring(st[p .. "invertDirection"] or false),
        }, "\t") .. "\n")
        dma:flush()
        if vmadd < 0x2000 or (vmadd >= 0x7000 and vmadd < 0x7400) then
          pending_capture = "dma_" .. hex(vmadd, 4) .. "_" .. tostring(dma_seq)
        end
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
  emu.cpuType.snes, emu.memType.snesMemory)

local port_seq = 0
local port_limit = 20000
emu.addMemoryCallback(function(address, value)
  if port_seq >= port_limit then return end
  local st = state()
  local vmadd = st["ppu.vramAddress"] or 0
  if vmadd < 0x2000 or (vmadd >= 0x7000 and vmadd < 0x7400) then
    port_seq = port_seq + 1
    ports:write(table.concat({
      tostring(port_seq), tostring(st["frameCount"] or 0), cpu_pc(st),
      hex(address, 4), hex(value, 2), hex(vmadd, 4),
    }, "\t") .. "\n")
    if port_seq % 128 == 0 then ports:flush() end
  end
end, emu.callbackType.write, 0x2118, 0x2119,
  emu.cpuType.snes, emu.memType.snesMemory)

local capture_count = 0
local capture_limit = 16
local last_capture_frame = -1000

local function sorted_state(st)
  local keys = {}
  for key, _ in pairs(st) do keys[#keys + 1] = key end
  table.sort(keys)
  local lines = {}
  for _, key in ipairs(keys) do
    lines[#lines + 1] = string.format("%s=%s", key, tostring(st[key]))
  end
  return table.concat(lines, "\n") .. "\n"
end

local function capture(reason, force)
  if capture_count >= capture_limit then return end
  local st = state()
  local frame = st["frameCount"] or 0
  if not force and frame - last_capture_frame < 20 then return end
  last_capture_frame = frame
  capture_count = capture_count + 1
  local stem = string.format("%02d_f%07d_%s", capture_count, frame, reason)

  local sf = assert(io.open(ROOT .. stem .. "_state.txt", "w"))
  sf:write(sorted_state(st))
  sf:close()
  write_blob(ROOT .. stem .. "_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(ROOT .. stem .. "_wram.bin", 0x7E0000, 0x20000, emu.memType.snesMemory)
  write_blob(ROOT .. stem .. "_cgram.bin", 0, 0x200, emu.memType.snesCgRam)
  write_blob(ROOT .. stem .. "_oam.bin", 0, 0x220, emu.memType.snesSpriteRam)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local pf = assert(io.open(ROOT .. stem .. "_screen.png", "wb"))
    pf:write(png)
    pf:close()
  end
  event("capture", stem, st)
  emu.displayMessage("ending logo", "dump " .. tostring(capture_count) .. ": " .. reason)
end

local stable_target_frames = 0
local last_stable_capture = -1000
emu.addEventCallback(function()
  local st = state()
  local frame = st["frameCount"] or 0
  if pending_capture then
    local reason = pending_capture
    pending_capture = nil
    capture(reason, false)
  end

  local tilemap = st["ppu.layers[0].tilemapAddress"] or -1
  local chr = st["ppu.layers[0].chrAddress"] or -1
  if tilemap == 0x7000 and chr == 0x0000 then
    stable_target_frames = stable_target_frames + 1
    if stable_target_frames == 2 or frame - last_stable_capture >= 120 then
      last_stable_capture = frame
      capture("bg1_tm7000_chr0000", true)
    end
  else
    stable_target_frames = 0
  end
end, emu.eventType.endFrame)

-- 스크립트를 목표 화면에서 켠 경우에도 현재 VRAM을 즉시 확보한다.
capture("script_start", true)
event("ready", "enter VICTORYS ending scene")
emu.displayMessage("ending logo", "trace ready - enter target scene")
