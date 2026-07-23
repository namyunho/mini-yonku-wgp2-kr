-- trace_stage_intro.lua
-- 챕터 시작 인트로(배경 위 일본어 제목)의 전용 그래픽 경로 추적기.
-- 세이브 파일 선택 화면에서 실행한 뒤 파일을 불러와 인트로까지 진행한다.

local TRACE_ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/stage_intro/"
local RUN_ID = os.date("%Y%m%d_%H%M%S")
local ROOT = TRACE_ROOT .. "run_" .. RUN_ID .. "/"
os.execute('mkdir -p "' .. ROOT .. '"')

local latest = assert(io.open(TRACE_ROOT .. "LATEST.txt", "w"))
latest:write(ROOT .. "\n")
latest:close()

local trace = assert(io.open(ROOT .. "trace.txt", "w"))
local start_frame = emu.getState()["frameCount"] or 0
-- 수동으로 연구소/어드벤처 장면을 넘기는 시간을 충분히 보장한다.
-- 관련 이벤트만 캡처하므로 10분 동안 켜 두어도 로그와 실행 부하는 작다.
local duration = 36000
local active = true
local seen = {}
local shot_count = 0
local capture_until = -1
local next_capture = -1
local wrote_trigger_wram = false
local direct_vram_writes = 0
local wram_title_writes = 0

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
  if not active then return end
  trace:write(row .. "\n")
  trace:flush()
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

local function snapshot(stem)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local f = assert(io.open(ROOT .. stem .. ".png", "wb")); f:write(png); f:close()
  end
  write_blob(ROOT .. stem .. "_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(ROOT .. stem .. "_oam.bin", 0, 0x220, emu.memType.snesSpriteRam)
  write_blob(ROOT .. stem .. "_cgram.bin", 0, 0x200, emu.memType.snesCgRam)
end

local function arm_capture(frame, reason)
  capture_until = math.max(capture_until, frame + 180)
  if next_capture < frame then next_capture = frame end
  add(state_line("capture-arm", "reason=" .. reason .. " until=" .. tostring(capture_until)))
end

-- 제목은 OBJ가 아니라 BG 2bpp 타일이며, 실측 VRAM byte $2000-$2DDF에 놓인다.
-- DMA 콜백이 발화하지 않는 Mesen 경로도 있으므로 VRAM 자체 쓰기에서 CPU PC를 잡는다.
emu.addMemoryCallback(function(address, value)
  if not active or direct_vram_writes >= 4096 then return end
  direct_vram_writes = direct_vram_writes + 1
  local st = emu.getState()
  local pc = ((st["cpu.k"] or 0) << 16) | (st["cpu.pc"] or 0)
  add_once(string.format("vram:%06X:%04X", pc, address & 0xFFF0),
    state_line("title-vram-write",
      "address=$" .. hex(address, 4) .. " value=$" .. hex(value, 2)))
  arm_capture(st["frameCount"] or 0, "title-vram-write")
end, emu.callbackType.write, 0x2000, 0x2DDF,
    emu.cpuType.snes, emu.memType.snesVideoRam)

-- 원본 화면에서는 후반 제목 타일과 고정 STAGE 표기가 $7F:1000대에 남는다.
-- 동적 제목을 생성하는 CPU PC를 찾기 위해 이 후보 버퍼의 쓰기 호출자를 기록한다.
emu.addMemoryCallback(function(address, value)
  if not active or wram_title_writes >= 4096 then return end
  wram_title_writes = wram_title_writes + 1
  local st = emu.getState()
  local pc = ((st["cpu.k"] or 0) << 16) | (st["cpu.pc"] or 0)
  add_once(string.format("wram:%06X:%06X", pc, address & 0xFFFFF0),
    state_line("title-wram-write",
      "address=$" .. hex(address, 6) .. " value=$" .. hex(value, 2)))
  arm_capture(st["frameCount"] or 0, "title-wram-write")
end, emu.callbackType.write, 0x7F1000, 0x7F4FFF,
    emu.cpuType.snes, emu.memType.snesMemory)

-- 공용 LZSS 소스와 호출자를 기록한다.
for _, address in ipairs({0xC00D52, 0xC00D91}) do
  emu.addMemoryCallback(function()
    if not active then return end
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

-- 공용 화면 선택기와 화면 그래픽 포인터 테이블.
emu.addMemoryCallback(function()
  if not active then return end
  local frame = emu.getState()["frameCount"] or 0
  add(state_line("screen-select", "screen=" .. tostring(read_cpu(0x7E712E))))
  arm_capture(frame, "screen-select")
end, emu.callbackType.exec, 0xC0AEB4, 0xC0AEB4,
    emu.cpuType.snes, emu.memType.snesMemory)

emu.addMemoryCallback(function()
  if not active then return end
  local st = emu.getState()
  local x = st["cpu.x"] or 0
  local lo = read_cpu(0xC20050 + x)
  local hi = read_cpu(0xC20051 + x)
  local bank = read_cpu(0xC20052 + x)
  add(state_line("screen-gfx-source",
    string.format("table_x=$%04X source=$%02X:%04X", x, bank, (hi << 8) | lo)))
  arm_capture(st["frameCount"] or 0, "screen-gfx-source")
end, emu.callbackType.exec, 0xC0AF7A, 0xC0AF7A,
    emu.cpuType.snes, emu.memType.snesMemory)

-- 세이브 파일용 $C0:830F 문자열 경로 및 공용 렌더러 후보와 인트로를 분리 판정한다.
for _, address in ipairs({
  0xC075D3, 0xC0761E, 0xC06634, 0xC06681, 0xC1965E, 0xC01B4B,
  0xC08DC2, 0xC08EDA, 0xC08FE2, 0xC0900F, 0xD051AA, 0xD051BB,
}) do
  emu.addMemoryCallback(function()
    if active then
      local frame = emu.getState()["frameCount"] or 0
      add(state_line("renderer-path", "hook=$" .. hex(address, 6)))
      arm_capture(frame, "renderer-path")
    end
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

emu.addMemoryCallback(function(address, value)
  if not active then return end
  local st = emu.getState()
  local caller = ((st["cpu.k"] or 0) << 16) | (st["cpu.pc"] or 0)
  add_once(string.format("title-read:%06X:%06X", address, caller),
    state_line("save-title-rom-read",
      "address=$" .. hex(address, 6) .. " value=$" .. hex(value, 2)))
end, emu.callbackType.read, 0xC08234, 0xC08322,
    emu.cpuType.snes, emu.memType.snesMemory)

-- WRAM을 거치는 경우까지 포함한 모든 VRAM DMA.
emu.addMemoryCallback(function(_, value)
  if not active then return end
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
        local vmadd = st["ppu.vramAddress"] or 0
        local first_byte = vmadd * 2
        local last_byte = first_byte + size - 1
        -- 실측 제목 2bpp 타일 byte $2000-$2DDF와 겹치는 전송만 남긴다.
        if first_byte <= 0x2DDF and last_byte >= 0x2000 then
          add(state_line("title-vram-dma", string.format(
            "ch=%d src=$%02X:%04X size=$%04X vmadd=$%04X",
            channel, bank, source, size, vmadd)))
          arm_capture(st["frameCount"] or 0, "title-vram-dma")
        end
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
    emu.cpuType.snes, emu.memType.snesMemory)

write_blob(ROOT .. "wram_start.bin", 0, 0x20000, emu.memType.snesWorkRam)
snapshot("frame_000_start")
add(state_line("session-start", "duration=" .. tostring(duration)))

emu.addEventCallback(function()
  if not active then return end
  local frame = emu.getState()["frameCount"] or 0
  local elapsed = frame - start_frame
  if frame >= next_capture and frame <= capture_until then
    shot_count = shot_count + 1
    snapshot(string.format("frame_%03d_f%d", shot_count, frame))
    next_capture = frame + 20
    if not wrote_trigger_wram then
      write_blob(ROOT .. "wram_trigger.bin", 0, 0x20000, emu.memType.snesWorkRam)
      wrote_trigger_wram = true
    end
  end
  if elapsed >= duration then
    write_blob(ROOT .. "wram_end.bin", 0, 0x20000, emu.memType.snesWorkRam)
    add(state_line("session-end", string.format(
      "shots=%d direct_vram_writes=%d wram_title_writes=%d",
      shot_count, direct_vram_writes, wram_title_writes)))
    active = false
    trace:close()
    emu.displayMessage("trace", "챕터 인트로 추적 완료")
  end
end, emu.eventType.endFrame)

emu.displayMessage("trace", "10분간 추적합니다. 챕터 인트로까지 진행해 주세요")
