# tts_service.py
import asyncio
import edge_tts

async def sintetizar_voz_neural(texto: str, voz: str = "es-MX-DaliaNeural") -> bytes:
    comunicador = edge_tts.Communicate(texto, voz, rate="+0%", pitch="+0Hz")
    buffer = bytearray()
    async for fragmento in comunicador.stream():
        if fragmento["type"] == "audio":
            buffer.extend(fragmento["data"])
    return bytes(buffer)