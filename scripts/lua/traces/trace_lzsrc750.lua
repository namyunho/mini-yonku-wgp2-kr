-- trace_lzsrc.lua : LZSS 디컴프레서 진입($C0:0D91)마다 소스 롱포인터($11-$13)·길이($05) 캡처.
--   → 오프닝 그래픽(크레딧·로고 등)의 압축 ROM 소스 주소 목록. 산출 tmp/trace/lz_src.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local rows = {}
local function onEntry()
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r(a) return emu.read(d + a, emu.memType.snesWorkRam) end
  local lo, mi, bk = r(0x11), r(0x12), r(0x13)
  local len = r(0x05) + r(0x06) * 256
  rows[#rows + 1] = string.format("f=%-4d src=$%02X:%04X (pc=0x%06X) len=$%04X(%d)",
    st["frameCount"], bk, mi * 256 + lo, ((bk % 0x40) * 0x10000) + (mi * 256 + lo), len, len)
end
emu.addMemoryCallback(onEntry, emu.callbackType.exec, 0xC00D91, 0xC00D91, emu.cpuType.snes, emu.memType.snesMemory)

local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  if fr == 750 and not done then
    done = true
    local f = io.open(ROOT .. "lz_src.txt", "w")
    if f then f:write("# LZSS 디컴프 진입별 소스·길이\n"); for _, s in ipairs(rows) do f:write(s .. "\n") end; f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
