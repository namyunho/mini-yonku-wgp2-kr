-- trace_d9caller.lua : $D9 폰트 디컴프 호출자 + 후속 VRAM DMA 포착 (재배치 패치용).
--   $C0:0D52 진입 시 소스 $11-$13·복귀주소(스택). 뱅크 $D9면 플래그.
--   이후 $420B DMA 중 VRAM 목적지 로그(src·dest·size). 사용자 수동 메뉴 이동.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/d9caller.txt"
local rows = {}
local armed = false
local function flush()
  local f = io.open(OUT, "w"); for _, s in ipairs(rows) do f:write(s .. "\n") end; f:close()
end

emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r(a) return emu.read(d + a, emu.memType.snesWorkRam) end
  local bk = r(0x13); local addr = r(0x11) + r(0x12) * 256
  -- 복귀주소: 스택포인터 s+1..s+3 (JSL 3바이트). $C0:0D52 진입 첫 명령이 PHB라 아직 안 밀림.
  local s = st["cpu.sp"]
  local rl = emu.read(s + 1, emu.memType.snesWorkRam)
  local rm = emu.read(s + 2, emu.memType.snesWorkRam)
  local rh = emu.read(s + 3, emu.memType.snesWorkRam)
  local ret = rh * 0x10000 + rm * 256 + rl  -- JSL은 (복귀-1) 저장
  if bk == 0xD9 then
    rows[#rows+1] = string.format("f=%d DECOMP src=$%02X:%04X caller_ret=$%06X", st["frameCount"], bk, addr, (ret + 1) & 0xFFFFFF)
    armed = true
    flush()
  end
end, emu.callbackType.exec, 0xC00D52, 0xC00D52, emu.cpuType.snes, emu.memType.snesMemory)

emu.addMemoryCallback(function(addr, value)
  if not armed then return end
  local st = emu.getState()
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]
      if dest == 0x18 or dest == 0x19 then
        local sb = st[p .. "srcBank"]; local sa = st[p .. "srcAddress"]
        local size = st[p .. "transferSize"]; if size == 0 then size = 65536 end
        local vmadd = st["ppu.vramAddress"]
        rows[#rows+1] = string.format("f=%d  DMA->VRAM vmadd=$%04X(tile %d) src=$%02X:%04X size=%d",
          st["frameCount"], vmadd, vmadd // 8, sb, sa, size)
        flush()
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)
