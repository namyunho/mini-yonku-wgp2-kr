-- trace_formation_blink.lua
-- 포메이션 선택 라벨의 교차 프레임 전용 추적기.
-- 실행 후 포메이션 화면을 나갔다 다시 들어와 한 항목을 10초 이상 선택한다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/formation_blink/"
os.execute('mkdir -p "' .. ROOT .. '"')

local rows = {}
local seen = {}
local armed_frame = nil
local shot_count = 0
local vram_count = 0

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function state_line(tag, extra)
  local st = emu.getState()
  return table.concat({
    "f=" .. tostring(st["frameCount"] or 0), tag,
    "pc=$" .. hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    "a=$" .. hex(st["cpu.a"], 4), "x=$" .. hex(st["cpu.x"], 4),
    "y=$" .. hex(st["cpu.y"], 4), "d=$" .. hex(st["cpu.d"], 4),
    "dbr=$" .. hex(st["cpu.dbr"], 2), extra or "",
  }, "\t")
end

local function add(row)
  rows[#rows + 1] = row
  local f = assert(io.open(ROOT .. "trace.txt", "a"))
  f:write(row .. "\n")
  f:close()
end

local function add_once(key, row)
  if seen[key] then return end
  seen[key] = true
  add(row)
end

local function read_cpu(address)
  return emu.read(address & 0xFFFFFF, emu.memType.snesMemory) & 0xFF
end

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local buffer = {}
  for i = 0, size - 1 do
    buffer[#buffer + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
    if #buffer == 4096 then f:write(table.concat(buffer)); buffer = {} end
  end
  if #buffer > 0 then f:write(table.concat(buffer)) end
  f:close()
end

local function screenshot(stem)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local f = assert(io.open(ROOT .. stem .. ".png", "wb")); f:write(png); f:close()
  end
end

local function vram_snapshot(stem)
  write_blob(ROOT .. stem .. "_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
end

-- 현재까지 확인한 세 포메이션 소스 설정 경로.
for _, address in ipairs({0xC169B7, 0xC174BF, 0xC3675C}) do
  emu.addMemoryCallback(function()
    local st = emu.getState()
    armed_frame = st["frameCount"] or 0
    shot_count = 0
    vram_count = 0
    add(state_line("formation-source-path", "hook=$" .. hex(address, 6)))
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- 공용 LZSS 진입의 실제 소스를 기록해 별도 선택 프레임 자원을 찾는다.
for _, address in ipairs({0xC00D52, 0xC00D91}) do
  emu.addMemoryCallback(function()
    local st = emu.getState()
    local d = st["cpu.d"] or 0
    local lo = read_cpu((d + 0x11) & 0xFFFF)
    local hi = read_cpu((d + 0x12) & 0xFFFF)
    local bank = read_cpu((d + 0x13) & 0xFFFF)
    local sp = st["cpu.sp"] or 0
    local ret_lo = read_cpu((sp + 1) & 0xFFFF)
    local ret_hi = read_cpu((sp + 2) & 0xFFFF)
    local ret_bank = read_cpu((sp + 3) & 0xFFFF)
    local ret = (((ret_bank << 16) | (ret_hi << 8) | ret_lo) + 1) & 0xFFFFFF
    local source = string.format("$%02X:%04X", bank, (hi << 8) | lo)
    add_once(string.format("lz:%06X:%s:%06X", address, source, ret),
      state_line("lzss", "entry=$" .. hex(address, 6) ..
        " source=" .. source .. " return=$" .. hex(ret, 6)))
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- 선택 애니메이션 중 발생하는 VRAM DMA를 모두 기록한다.
emu.addMemoryCallback(function(_, value)
  if not armed_frame then return end
  local st = emu.getState()
  for channel = 0, 7 do
    if (value & (1 << channel)) ~= 0 then
      local prefix = "dmaController.channel[" .. channel .. "]."
      local dest = st[prefix .. "destAddress"]
      if dest == 0x18 or dest == 0x19 then
        local bank = st[prefix .. "srcBank"] or 0
        local source = st[prefix .. "srcAddress"] or 0
        local size = st[prefix .. "transferSize"] or 0
        if size == 0 then size = 65536 end
        add(state_line("vram-dma", string.format(
          "ch=%d src=$%02X:%04X size=$%04X vmadd=$%04X",
          channel, bank, source, size, st["ppu.vramAddress"] or 0)))
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
    emu.cpuType.snes, emu.memType.snesMemory)

emu.addEventCallback(function()
  local frame = emu.getState()["frameCount"] or 0
  if armed_frame and frame >= armed_frame and frame <= armed_frame + 720 and
      frame % 2 == 0 then
    screenshot(string.format("screen_%03d_f%d", shot_count, frame))
    shot_count = shot_count + 1
  end
  if armed_frame and frame >= armed_frame and frame <= armed_frame + 720 and
      frame % 10 == 0 then
    vram_snapshot(string.format("vram_%03d_f%d", vram_count, frame))
    vram_count = vram_count + 1
  end
end, emu.eventType.endFrame)

armed_frame = emu.getState()["frameCount"] or 0
shot_count = 0
vram_count = 0
add("--- session-start immediate-frame=" .. tostring(armed_frame) .. " ---")
emu.displayMessage("trace", "화면 이동 없이 현재 항목을 10초간 선택해 두세요")
