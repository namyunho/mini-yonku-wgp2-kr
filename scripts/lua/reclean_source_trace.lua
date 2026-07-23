-- reclean_source_trace.lua
-- 원본 ROM 화면에서 독립적으로 찾은 C7:Bxxx 타일 스트림의 소비자를 추적한다.
-- 기존 문서/훅 주소는 사용하지 않는다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/reclean_source_trace/"
os.execute('mkdir -p "' .. ROOT .. '"')

local trace = assert(io.open(ROOT .. "rom_reads.tsv", "w"))
trace:write("frame\taddress\tvalue\tcaller\ta\tx\ty\tsp\tdbr\n")
trace:flush()

local dma = assert(io.open(ROOT .. "vram_dma.tsv", "w"))
dma:write("frame\tcaller\tchannel\tsource\tsize\tvmadd\n")
dma:flush()

local counts = {}
local total = 0

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function trace_rom_read(address, value)
  if total >= 20000 then return end

  local st = emu.getState()
  local bank = st["cpu.k"] or 0
  local pc = st["cpu.pc"] or 0
  local key = string.format("%02X:%04X>%06X", bank, pc, address)
  counts[key] = (counts[key] or 0) + 1
  total = total + 1

  trace:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(address, 6),
    hex(value, 2),
    hex(bank, 2) .. ":" .. hex(pc, 4),
    hex(st["cpu.a"], 4),
    hex(st["cpu.x"], 4),
    hex(st["cpu.y"], 4),
    hex(st["cpu.sp"], 4),
    hex(st["cpu.dbr"], 2),
  }, "\t") .. "\n")
  trace:flush()
end

local rom_ranges = {
  {0x07B000, 0x07BFFF}, {0x47B000, 0x47BFFF},
  {0x87B000, 0x87BFFF}, {0xC7B000, 0xC7BFFF},
  {0x01C000, 0x01CFFF}, {0x41C000, 0x41CFFF},
  {0x81C000, 0x81CFFF}, {0xC1C000, 0xC1CFFF},
  {0x03A000, 0x03AFFF}, {0x43A000, 0x43AFFF},
  {0x83A000, 0x83AFFF}, {0xC3A000, 0xC3AFFF},
}
for _, range in ipairs(rom_ranges) do
  emu.addMemoryCallback(trace_rom_read, emu.callbackType.read,
      range[1], range[2], emu.cpuType.snes, emu.memType.snesMemory)
end

local wram = assert(io.open(ROOT .. "wram_writes.tsv", "w"))
wram:write("frame\taddress\tvalue\tcaller\ta\tx\ty\tdbr\n")
wram:flush()
local wram_total = 0
local function trace_wram_write(address, value)
  if wram_total >= 30000 then return end
  wram_total = wram_total + 1
  local st = emu.getState()
  wram:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(address, 6),
    hex(value, 2),
    hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    hex(st["cpu.a"], 4),
    hex(st["cpu.x"], 4),
    hex(st["cpu.y"], 4),
    hex(st["cpu.dbr"], 2),
  }, "\t") .. "\n")
  if wram_total % 256 == 0 then wram:flush() end
end
emu.addMemoryCallback(trace_wram_write, emu.callbackType.write,
    0x7EA600, 0x7EB2FF, emu.cpuType.snes, emu.memType.snesMemory)
emu.addMemoryCallback(trace_wram_write, emu.callbackType.write,
    0x7E5900, 0x7E5FFF, emu.cpuType.snes, emu.memType.snesMemory)

emu.addMemoryCallback(function(_, mask)
  local st = emu.getState()
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local p = "dmaController.channel[" .. channel .. "]."
      if (st[p .. "destAddress"] or 0) == 0x18 then
        dma:write(table.concat({
          tostring(st["frameCount"] or 0),
          hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
          tostring(channel),
          hex(st[p .. "srcBank"], 2) .. ":" .. hex(st[p .. "srcAddress"], 4),
          tostring(st[p .. "transferSize"] or 0),
          hex(st["ppu.vramAddress"], 4),
        }, "\t") .. "\n")
        dma:flush()
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
    emu.cpuType.snes, emu.memType.snesMemory)

local hdma = assert(io.open(ROOT .. "hdma.tsv", "w"))
hdma:write("frame\tcaller\tmask\tchannel\tcontrol\tdest\ttable\ttable_bank\tindirect_bank\n")
hdma:flush()

emu.addMemoryCallback(function(_, mask)
  local st = emu.getState()
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local p = "dmaController.channel[" .. channel .. "]."
      hdma:write(table.concat({
        tostring(st["frameCount"] or 0),
        hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
        hex(mask, 2),
        tostring(channel),
        hex(st[p .. "transferMode"], 2),
        "21" .. hex(st[p .. "destAddress"], 2),
        hex(st[p .. "srcAddress"], 4),
        hex(st[p .. "srcBank"], 2),
        hex(st[p .. "hdmaBank"], 2),
      }, "\t") .. "\n")
    end
  end
  hdma:flush()
end, emu.callbackType.write, 0x420C, 0x420C,
    emu.cpuType.snes, emu.memType.snesMemory)

local blob = assert(io.open(ROOT .. "blob_loads.tsv", "w"))
blob:write("frame\tcaller\tsource\tdp\n")
blob:flush()
emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"] or 0
  local lo = emu.read(d + 1, emu.memType.snesMemory) & 0xFF
  local hi = emu.read(d + 2, emu.memType.snesMemory) & 0xFF
  local bank = emu.read(d + 3, emu.memType.snesMemory) & 0xFF
  blob:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    hex(bank, 2) .. ":" .. hex(hi, 2) .. hex(lo, 2),
    hex(d, 4),
  }, "\t") .. "\n")
  blob:flush()
end, emu.callbackType.exec, 0xC0AD6F, 0xC0AD6F,
    emu.cpuType.snes, emu.memType.snesMemory)

-- The same D9 resource is decompressed at two C3 call sites.  Trace both so
-- the tutorial-specific load can be distinguished from unrelated scenes
-- without assuming either call site's purpose from static layout alone.
local font_calls = assert(io.open(ROOT .. "font_calls.tsv", "w"))
font_calls:write("frame\tcallsite\ta\tx\ty\tsp\tdbr\n")
font_calls:flush()

local function trace_font_call()
  local st = emu.getState()
  font_calls:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    hex(st["cpu.a"], 4),
    hex(st["cpu.x"], 4),
    hex(st["cpu.y"], 4),
    hex(st["cpu.sp"], 4),
    hex(st["cpu.dbr"], 2),
  }, "\t") .. "\n")
  font_calls:flush()
end

for _, callsite in ipairs({
  0x839DCB, 0x83A83B, 0x8094DA,
  0xC39DCB, 0xC3A83B, 0xC094DA,
}) do
  emu.addMemoryCallback(trace_font_call, emu.callbackType.exec,
      callsite, callsite, emu.cpuType.snes, emu.memType.snesMemory)
end

local decompress_calls = assert(io.open(ROOT .. "decompress_calls.tsv", "w"))
decompress_calls:write("frame\tentry\treturn_to\tsp\ta\tx\ty\tdbr\n")
decompress_calls:flush()

local function trace_decompress_call()
  local st = emu.getState()
  local sp = st["cpu.sp"] or 0
  local ret_lo = emu.read((sp + 1) & 0xFFFF, emu.memType.snesMemory) & 0xFF
  local ret_hi = emu.read((sp + 2) & 0xFFFF, emu.memType.snesMemory) & 0xFF
  local ret_bank = emu.read((sp + 3) & 0xFFFF, emu.memType.snesMemory) & 0xFF
  -- JSL stores the address of its last operand byte.  RTL adds one.
  local ret_pc = ((ret_hi << 8) | ret_lo) + 1
  decompress_calls:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    hex(ret_bank, 2) .. ":" .. hex(ret_pc & 0xFFFF, 4),
    hex(sp, 4),
    hex(st["cpu.a"], 4),
    hex(st["cpu.x"], 4),
    hex(st["cpu.y"], 4),
    hex(st["cpu.dbr"], 2),
  }, "\t") .. "\n")
  decompress_calls:flush()
end

for _, entry in ipairs({0x800D52, 0xC00D52}) do
  emu.addMemoryCallback(trace_decompress_call, emu.callbackType.exec,
      entry, entry, emu.cpuType.snes, emu.memType.snesMemory)
end

local direct_calls = assert(io.open(ROOT .. "direct_calls.tsv", "w"))
direct_calls:write("frame\tentry\ta\tx\ty\tsp\tdbr\n")
direct_calls:flush()

local function trace_direct_call()
  local st = emu.getState()
  direct_calls:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    hex(st["cpu.a"], 4),
    hex(st["cpu.x"], 4),
    hex(st["cpu.y"], 4),
    hex(st["cpu.sp"], 4),
    hex(st["cpu.dbr"], 2),
  }, "\t") .. "\n")
  direct_calls:flush()
end

for _, entry in ipairs({0x801B4B, 0xC01B4B}) do
  emu.addMemoryCallback(trace_direct_call, emu.callbackType.exec,
      entry, entry, emu.cpuType.snes, emu.memType.snesMemory)
end

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local bytes = {}
  for i = 0, size - 1 do
    bytes[#bytes + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
    if #bytes == 4096 then
      f:write(table.concat(bytes))
      bytes = {}
    end
  end
  if #bytes > 0 then f:write(table.concat(bytes)) end
  f:close()
end

local function dump_latest()
  local st = emu.getState()
  local sf = assert(io.open(ROOT .. "live_state.txt", "w"))
  local keys = {}
  for key, _ in pairs(st) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    sf:write(string.format("%s=%s\n", key, tostring(st[key])))
  end
  sf:close()
  write_blob(ROOT .. "live_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(ROOT .. "live_wram.bin", 0x7E0000, 0x20000, emu.memType.snesMemory)
  write_blob(ROOT .. "live_oam.bin", 0, 0x220, emu.memType.snesSpriteRam)
  write_blob(ROOT .. "live_cgram.bin", 0, 0x200, emu.memType.snesCgRam)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local pf = assert(io.open(ROOT .. "live_screen.png", "wb"))
    pf:write(png)
    pf:close()
  end
end

local ticks = 0
emu.addEventCallback(function()
  ticks = ticks + 1
  local st = emu.getState()
  local frame = st["frameCount"] or 0
  if frame % 120 == 0 then
    local summary = assert(io.open(ROOT .. "summary.tsv", "w"))
    summary:write("count\tcaller>address\n")
    local keys = {}
    for key, _ in pairs(counts) do keys[#keys + 1] = key end
    table.sort(keys)
    for _, key in ipairs(keys) do
      summary:write(tostring(counts[key]) .. "\t" .. key .. "\n")
    end
    summary:close()
  end
  if ticks == 10 or ticks % 180 == 0 then dump_latest() end
end, emu.eventType.endFrame)

emu.displayMessage("reclean", "독립 ROM read trace: C7:B000-C7:BFFF")
