"""
Motor de Diagnóstico Automático em Modo Somente Leitura (core/diagnostics_engine.py).
Implementa a Etapa 2 do Storage Rescue (Nível 1 de Segurança — 100% Somente Leitura).

Identifica automaticamente os 12 cenários técnicos da especificação:
1. Disco reconhecido sem partição.
2. Disco sem letra de unidade.
3. Partição RAW.
4. Espaço não alocado.
5. Disco offline.
6. Disco não inicializado.
7. Dispositivo USB com 0 bytes.
8. Dispositivo identificado como No Media.
9. Falha de comunicação USB (incluindo seriais de erro de ponte USB e falhas PnP).
10. Capacidade divergente da capacidade esperada.
11. Erros de leitura (SMART e Eventos de E/S do Kernel Windows Event ID 153/7/51).
12. Possíveis problemas de integridade.

Inclui também o Varredor de Barramento USB / PnP para diagnosticar pendrives e SSDs
que não aparecem no comando 'list disk' do DiskPart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple
import winreg

from core.logger import logger
from core.models import DiskDevice, HealthStatus, format_bytes


@dataclass
class DiagnosticFinding:
    """
    Representa um problema ou constatação técnica encontrada durante o diagnóstico.
    Segue rigorosamente a estrutura de experiência do usuário (Seções 4 e 12):
    - O que foi encontrado (title / diagnosis)
    - O que significa (meaning)
    - Qual é a possível causa (possible_causes)
    - Quais são os riscos (risks)
    - Qual é o próximo passo recomendado (recommendation)
    """

    code: str
    title: str
    severity: HealthStatus
    diagnosis: str
    meaning: str
    possible_causes: List[str] = field(default_factory=list)
    risks: str = ""
    recommendation: str = ""


@dataclass
class UsbBusDiagnosticItem:
    """
    Representa um dispositivo USB ou evento de E/S detectado no histórico PnP
    ou no Log de Eventos do Kernel que explica por que um pendrive/disco não aparece
    ou falha intermitentemente no 'list disk'.
    """

    category: str          # "FALHA_DESCRITOR_USB", "DISPOSITIVO_DESCONECTADO", "ERRO_IO_DISCO"
    name: str
    instance_id: str
    status: str
    last_arrival: str = "—"
    last_removal: str = "—"
    severity: HealthStatus = HealthStatus.WARNING
    explanation: str = ""
    possible_causes: List[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class DeviceDiagnosticReport:
    """Laudo consolidado de diagnóstico para um dispositivo físico."""

    device: DiskDevice
    overall_status: HealthStatus
    findings: List[DiagnosticFinding] = field(default_factory=list)

    def format_plain_text(self) -> str:
        """
        Gera o laudo técnico em texto claro no formato exato exemplificado na Seção 4
        da especificação do projeto.
        """
        lines = [
            f"DISPOSITIVO: {self.device.model} (Disco {self.device.disk_number} — {self.device.manufacturer})",
            f"SERIAL: {self.device.serial_number}",
            f"CONEXÃO: {self.device.connection_type} | ESTILO: {self.device.partition_style}",
            f"CAPACIDADE: {self.device.capacity_formatted}",
            f"STATUS GERAL: {self.overall_status.value.upper()}",
            "-" * 76,
        ]
        for idx, f in enumerate(self.findings, start=1):
            lines.append(f"[{idx}] {f.title.upper()} ({f.severity.value})")
            lines.append("DIAGNÓSTICO:")
            lines.append(f"  {f.diagnosis}")
            lines.append("O QUE SIGNIFICA:")
            lines.append(f"  {f.meaning}")
            if f.possible_causes:
                lines.append("POSSÍVEIS CAUSAS:")
                for cause in f.possible_causes:
                    lines.append(f"  - {cause}")
            if f.risks:
                lines.append("RISCOS:")
                lines.append(f"  {f.risks}")
            lines.append("RECOMENDAÇÃO:")
            lines.append(f"  {f.recommendation}")
            lines.append("-" * 76)
        return "\n".join(lines)


def _extract_expected_capacity_bytes_from_model(model: str) -> Optional[int]:
    """
    Infere a capacidade nominal esperada (em bytes decimais de fabricante) a partir do nome
    do modelo do disco (ex: '480G', '500GB', '512G', '1TB', '1000DM', '240GB').
    """
    mdl = (model or "").upper()

    # Padrões explícitos como 480G, 512GB, 1TB, 2TB
    match_explicit = re.search(r"\b(\d{2,4})\s*(GB|G|TB|T)\b", mdl)
    if match_explicit:
        val = int(match_explicit.group(1))
        unit = match_explicit.group(2)
        if unit.startswith("T") and val <= 24:
            return val * 1_000_000_000_000
        if unit.startswith("G") and 16 <= val <= 8000:
            return val * 1_000_000_000

    # Padrões embutidos em códigos de modelo (ex: SD8SBBU480G1122, MZ7TN512HDHP, ST1000DM010)
    match_embedded_gb = re.search(r"(?:SSD|SD\w+|MZ\w+?)(120|128|240|250|256|480|500|512|960|1000|2000)G?", mdl)
    if match_embedded_gb:
        return int(match_embedded_gb.group(1)) * 1_000_000_000

    match_seagate = re.search(r"\bST(500|1000|2000|3000|4000)[A-Z]{2}", mdl)
    if match_seagate:
        return int(match_seagate.group(1)) * 1_000_000_000

    return None


class DiagnosticsEngine:
    """
    Motor de diagnóstico somente leitura (Nível 1 de Segurança).
    Analisa dispositivos inventariados e o barramento USB/PnP sem realizar escritas.
    """

    def diagnose_all_devices(
        self,
        devices: List[DiskDevice],
        io_events_by_disk: Optional[Dict[int, List[str]]] = None,
    ) -> List[DeviceDiagnosticReport]:
        """Executa o diagnóstico completo para todos os dispositivos fornecidos."""
        reports: List[DeviceDiagnosticReport] = []
        for dev in devices:
            disk_events = (io_events_by_disk or {}).get(dev.disk_number, [])
            reports.append(self.diagnose_device(dev, disk_io_events=disk_events))
        return reports

    def diagnose_device(
        self,
        device: DiskDevice,
        disk_io_events: Optional[List[str]] = None,
    ) -> DeviceDiagnosticReport:
        """
        Aplica as 12 regras de diagnóstico sobre um DiskDevice em modo somente leitura.
        """
        findings: List[DiagnosticFinding] = []
        io_events = disk_io_events or []

        # 1. Dispositivo USB com 0 bytes / No Media (Cenários 7, 8 e 9)
        if device.is_no_media or device.is_zero_bytes or device.capacity_bytes <= 0:
            findings.append(
                DiagnosticFinding(
                    code="USB_NO_MEDIA_0_BYTES",
                    title="Dispositivo com 0 bytes / Sem Mídia Reconhecida (No Media)",
                    severity=HealthStatus.CRITICAL,
                    diagnosis=(
                        "O controlador USB foi identificado, mas não foi possível reconhecer "
                        "a mídia de armazenamento (Capacidade reportada: 0 bytes)."
                    ),
                    meaning=(
                        "O chip conversor USB (bridge SATA/NVMe-USB ou controlador interno do pendrive) "
                        "comunicou-se com a porta USB do Windows, porém a memória flash NAND ou o disco "
                        "conectado ao adaptador não respondeu aos comandos de leitura de geometria."
                    ),
                    possible_causes=[
                        "Adaptador SATA/USB ou case externo defeituoso.",
                        "Mau contato no conector USB ou SATA.",
                        "Falha de alimentação elétrica na porta USB (especialmente em HDs/SSDs externos).",
                        "Defeito eletrônico no controlador ou na memória NAND do SSD/Pendrive.",
                        "Firmware do SSD/Pendrive travado em modo de segurança (ROM Mode).",
                    ],
                    risks=(
                        "Qualquer tentativa de formatação ou inicialização falhará com erro de E/S "
                        "e pode agravar a degradação caso haja falha física intermitente."
                    ),
                    recommendation=(
                        "Testar outro adaptador ou conexão SATA/NVMe direta na placa-mãe antes de "
                        "tentar inicializar ou formatar."
                    ),
                )
            )

        # 2. Falha de comunicação USB / Ponte USB com serial genérico de erro
        serial_clean = (device.serial_number or "").strip()
        if device.is_usb and not device.is_no_media:
            if set(serial_clean) == {"0"} or "190610101002888" in serial_clean:
                findings.append(
                    DiagnosticFinding(
                        code="USB_BRIDGE_FALLBACK_SERIAL",
                        title="Possível Instabilidade na Ponte/Adaptador USB",
                        severity=HealthStatus.WARNING,
                        diagnosis=(
                            f"O dispositivo USB apresentou número de série genérico de controladora "
                            f"({serial_clean}) em vez do serial nativo da mídia."
                        ),
                        meaning=(
                            "Alguns adaptadores SATA/USB substituem o serial real do SSD/HD ou entram "
                            "em modo genérico quando há instabilidade de comunicação SAT (SCSI-ATA Translation)."
                        ),
                        possible_causes=[
                            "Ponte USB genérica (Initio, JMicron, ASMedia) ocultando dados nativos do disco.",
                            "Queda de tensão na porta USB frontal do gabinete.",
                            "Cabo USB longo ou com oxidação nos contatos.",
                        ],
                        risks=(
                            "Pode impedir a leitura dos atributos SMART reais e causar desconexões "
                            "durante transferências pesadas."
                        ),
                        recommendation=(
                            "Conectar preferencialmente nas portas USB 3.0 traseiras soldadas diretamente "
                            "na placa-mãe ou via porta SATA nativa para diagnóstico físico profundo."
                        ),
                    )
                )

        # 3. Disco Offline (Cenário 5)
        if device.is_offline and not device.is_no_media:
            findings.append(
                DiagnosticFinding(
                    code="DISK_OFFLINE",
                    title="Disco em Estado Offline",
                    severity=HealthStatus.WARNING,
                    diagnosis="O disco físico foi reconhecido, mas encontra-se marcado como Offline pelo Windows.",
                    meaning=(
                        "O sistema operacional desativou a montagem automática dos volumes deste disco "
                        "para evitar conflitos ou alterações acidentais."
                    ),
                    possible_causes=[
                        "Colisão de assinatura de disco (Disk Signature Collision) com outro disco clonado.",
                        "Política SAN do Windows configurada para manter discos externos offline.",
                        "Desativação manual anterior via Gerenciamento de Disco ou DiskPart.",
                    ],
                    risks="Os arquivos estão preservados, mas inacessíveis no Windows Explorer enquanto o disco estiver Offline.",
                    recommendation=(
                        "Utilizar o Módulo de Recuperação Lógica (Nível 2) para colocar o disco Online "
                        "após verificar se não há outro disco clonado conectado simultaneamente."
                    ),
                )
            )

        # 4. Disco Não Inicializado (Cenário 6)
        if device.is_uninitialized and not device.is_no_media:
            findings.append(
                DiagnosticFinding(
                    code="DISK_UNINITIALIZED",
                    title="Disco Não Inicializado (Sem Assinatura MBR ou GPT)",
                    severity=HealthStatus.WARNING,
                    diagnosis=(
                        "O disco possui capacidade física válida, mas não apresenta tabela de partições "
                        "MBR ou GPT reconhecida (Estilo reportado: RAW / Não Inicializado)."
                    ),
                    meaning=(
                        "O setor zero (LBA 0 / MBR ou cabeçalho GPT primário) está zerado, corrompido "
                        "ou trata-se de uma unidade nova de fábrica."
                    ),
                    possible_causes=[
                        "Disco ou SSD novo que ainda não foi particionado.",
                        "Execução anterior do comando 'clean' no DiskPart.",
                        "Corrupção do setor LBA 0 por remoção abrupta ou queda de energia.",
                        "Criptografia de disco inteiro ou sistema de arquivos proprietário (Linux/Mac/DVR).",
                    ],
                    risks=(
                        "ATENÇÃO: Inicializar ou criar nova tabela GPT/MBR sobrescreve os ponteiros de partição. "
                        "Se o disco contém dados importantes, NÃO inicialize antes de escanear partições perdidas."
                    ),
                    recommendation=(
                        "Se o disco contém dados importantes, utilize recuperação de partições antes de inicializar. "
                        "Se for um disco vazio para reuso, utilize o Módulo de Preparação Segura (Etapa 6)."
                    ),
                )
            )

        # 5. Disco Reconhecido Sem Partição (Cenário 1)
        if not device.is_no_media and not device.is_uninitialized and len(device.partitions) == 0:
            findings.append(
                DiagnosticFinding(
                    code="DISK_NO_PARTITIONS",
                    title="Disco Reconhecido Sem Partições Alocadas",
                    severity=HealthStatus.WARNING,
                    diagnosis=(
                        f"O disco possui tabela {device.partition_style}, mas nenhuma partição ativa "
                        "foi encontrada (100% do espaço está não alocado)."
                    ),
                    meaning="A tabela de partições existe, porém todas as partições foram excluídas ou ainda não foram criadas.",
                    possible_causes=[
                        "Exclusão manual de volume no Gerenciamento de Disco.",
                        "Interrupção durante um processo de formatação ou reparticionamento.",
                        "Tabela de partições recém-inicializada.",
                    ],
                    risks="O disco não aparecerá no Windows Explorer até que uma partição seja recuperada ou criada.",
                    recommendation=(
                        "Caso existissem arquivos anteriormente, verifique partições ocultas/excluídas no Módulo de "
                        "Recuperação Lógica. Caso contrário, crie uma nova partição primária."
                    ),
                )
            )

        # 6. Partição RAW (Cenário 3)
        raw_parts = [
            p for p in device.partitions if (p.volume and p.volume.is_raw) or "RAW" in p.partition_type.upper()
        ]
        if (device.has_raw_partition or raw_parts) and not device.is_no_media and not device.is_uninitialized:
            letters_str = ", ".join(
                f"{p.drive_letter}:" if p.drive_letter else f"Partição #{p.partition_number}"
                for p in raw_parts
            ) or device.file_systems_summary
            findings.append(
                DiagnosticFinding(
                    code="PARTITION_RAW",
                    title=f"Partição em Formato RAW Detectada ({letters_str})",
                    severity=HealthStatus.WARNING,
                    diagnosis=(
                        f"A partição ({letters_str}) está presente na tabela de partições, mas o Windows "
                        "não conseguiu identificar um sistema de arquivos válido (NTFS, exFAT ou FAT32)."
                    ),
                    meaning=(
                        "O setor de boot do volume (VBR) ou a Tabela Mestre de Arquivos ($MFT / FAT) "
                        "sofreu corrupção lógica, ou o volume utiliza um sistema de arquivos não nativo do Windows."
                    ),
                    possible_causes=[
                        "Remoção do pendrive/HD externo sem 'Remover Hardware com Segurança' durante gravação.",
                        "Queda de energia ou desligamento forçado do computador.",
                        "Setores defeituosos (Bad Blocks) exatamente no início da partição.",
                        "Partição formatada em ext4 (Linux), APFS/HFS+ (macOS) ou criptografada (BitLocker/VeraCrypt).",
                    ],
                    risks=(
                        "NUNCA aceite a mensagem do Windows 'Você precisa formatar o disco antes de usá-lo' "
                        "se desejar recuperar os arquivos. Formatar apagará o índice de arquivos."
                    ),
                    recommendation=(
                        "1. Verifique a saúde SMART primeiro para descartar defeito físico.\n"
                        "  2. Inspecione o volume no Módulo de Recuperação Lógica (Nível 2) sem formatar."
                    ),
                )
            )

        # 7. Disco / Partição de Dados Sem Letra de Unidade (Cenário 2)
        unmounted_data_parts = [
            p
            for p in device.partitions
            if not p.drive_letter
            and not p.is_system
            and not any(
                t in p.partition_type.upper()
                for t in ("SYSTEM", "RESERVED", "RECOVERY", "EFI")
            )
        ]
        if unmounted_data_parts and not device.is_no_media:
            part_desc = ", ".join(
                f"Partição #{p.partition_number} ({format_bytes(p.size_bytes)})"
                for p in unmounted_data_parts
            )
            findings.append(
                DiagnosticFinding(
                    code="PARTITION_MISSING_DRIVE_LETTER",
                    title=f"Partição de Dados Sem Letra de Unidade ({part_desc})",
                    severity=HealthStatus.WARNING,
                    diagnosis=(
                        f"Encontrada(s) {len(unmounted_data_parts)} partição(ões) de dados íntegra(s) "
                        f"({part_desc}), porém sem letra de unidade atribuída (ex: E:, F:)."
                    ),
                    meaning=(
                        "O dispositivo e seus arquivos estão presentes no sistema, mas como não há uma letra "
                        "montada no Gerenciador de Volumes, a unidade fica invisível no 'Este Computador'."
                    ),
                    possible_causes=[
                        "Conflito de letra de unidade previamente utilizada por outro pendrive ou unidade de rede.",
                        "Automount do Windows desabilitado ou falha ao registrar o GUID do volume no MountMgr.",
                        "Partição marcada com atributo de volume oculto.",
                    ],
                    risks="Baixo risco aos dados. É um problema puramente lógico de endereçamento no Windows.",
                    recommendation=(
                        "Atribuir uma letra de unidade livre utilizando a ferramenta 'Atribuir Letra de Unidade' "
                        "no Módulo de Recuperação Lógica (Nível 2 — operação 100% não destrutiva)."
                    ),
                )
            )

        # 8. Espaço Não Alocado Relevante (> 100 MB) (Cenário 4)
        if not device.is_no_media and device.unallocated_bytes > 100 * 1024 * 1024:
            findings.append(
                DiagnosticFinding(
                    code="UNALLOCATED_SPACE",
                    title=f"Espaço Não Alocado Detectado ({format_bytes(device.unallocated_bytes)})",
                    severity=HealthStatus.WARNING,
                    diagnosis=(
                        f"O disco possui {format_bytes(device.unallocated_bytes)} de capacidade física "
                        "fora de qualquer partição ativa."
                    ),
                    meaning=(
                        "Parte da capacidade real do dispositivo não está sendo aproveitada pelos volumes atuais "
                        "ou pertencia a uma partição que foi apagada."
                    ),
                    possible_causes=[
                        "Clonagem de um disco menor para um disco maior sem expansão da partição final.",
                        "Formatação em MBR de disco maior que 2 TB (limite arquitetural do MBR).",
                        "Exclusão acidental de uma partição secundária.",
                        "Gravação de imagem ISO menor que a capacidade total do pendrive.",
                    ],
                    risks="Desperdício de capacidade útil ou inacessibilidade a uma partição antiga excluída.",
                    recommendation=(
                        "Verifique se o espaço corresponde a uma partição apagada ou se deseja estender/criar "
                        "um novo volume para aproveitar 100% da capacidade."
                    ),
                )
            )

        # 9. Capacidade Divergente da Capacidade Esperada (Cenário 10)
        expected_cap = _extract_expected_capacity_bytes_from_model(device.model)
        if expected_cap and device.capacity_bytes > 0:
            ratio = device.capacity_bytes / float(expected_cap)
            if ratio < 0.85 or ratio > 1.15:
                findings.append(
                    DiagnosticFinding(
                        code="CAPACITY_MISMATCH",
                        title="Capacidade Real Divergente do Modelo Nominal",
                        severity=HealthStatus.CRITICAL,
                        diagnosis=(
                            f"O modelo '{device.model}' sugere cerca de {format_bytes(expected_cap)}, "
                            f"mas a capacidade física lida foi {device.capacity_formatted}."
                        ),
                        meaning=(
                            "Há uma discrepância anormal entre a capacidade anunciada na identificação do firmware "
                            "e o espaço real endereçável por setores LBA."
                        ),
                        possible_causes=[
                            "Configuração HPA (Host Protected Area) ou DCO limitando os setores visíveis do disco.",
                            "Falha em bancos de memória NAND de um SSD (modo de capacidade reduzida).",
                            "Pendrive/SSD falsificado com firmware adulterado.",
                        ],
                        risks="Alto risco de corrupção silenciosa de arquivos caso a mídia tenha células defeituosas ou adulteradas.",
                        recommendation=(
                            "Executar o Teste de Integridade e Verificação de Capacidade Real (Etapa 7) e inspecionar "
                            "os parâmetros SMART detalhados."
                        ),
                    )
                )

        # 10. Erros de Leitura e Retentativas de E/S no Kernel / SMART (Cenário 11)
        read_err_count = device.smart_info.read_errors_total or 0
        uncorr_count = device.smart_info.uncorrectable_errors or 0
        if io_events or uncorr_count > 0:
            ev_summary = "; ".join(io_events[:3]) if io_events else f"{uncorr_count} erro(s) não corrigíveis SMART"
            findings.append(
                DiagnosticFinding(
                    code="READ_IO_ERRORS",
                    title="Erros de Leitura / Retentativas de E/S Detectados",
                    severity=HealthStatus.CRITICAL if uncorr_count > 0 else HealthStatus.WARNING,
                    diagnosis=(
                        f"Foram registrados eventos de falha ou repetição de leitura de blocos lógicos (LBA) "
                        f"neste dispositivo: {ev_summary}."
                    ),
                    meaning=(
                        "O controlador de armazenamento precisou repetir leituras ou falhou ao ler setores "
                        "físicos dentro do tempo limite (timeout de E/S)."
                    ),
                    possible_causes=[
                        "Setores físicos degradados (Bad Blocks) na superfície magnética ou células NAND.",
                        "Cabo SATA/USB com ruído de sinal ou mau contato elétrico.",
                        "Fonte de alimentação ou porta USB incapaz de suprir picos de corrente de leitura.",
                    ],
                    risks=(
                        "Travamentos severos do Windows Explorer (congelamento de 30 a 90 segundos) e risco "
                        "de perda definitiva dos arquivos localizados nos setores afetados."
                    ),
                    recommendation=(
                        "Fazer backup imediato dos arquivos críticos antes de qualquer teste intensivo e "
                        "substituir o cabo/adaptador para isolar falha física da mídia."
                    ),
                )
            )
        elif read_err_count > 0:
            findings.append(
                DiagnosticFinding(
                    code="SMART_READ_RETRIES",
                    title=f"Contagem de Erros de Leitura Recuperados ({read_err_count})",
                    severity=HealthStatus.WARNING,
                    diagnosis=f"O contador de confiabilidade registra {read_err_count} erro(s) de leitura corrigidos por ECC.",
                    meaning="O disco precisou acionar correção de erro de hardware durante leituras anteriores.",
                    possible_causes=["Início de desgaste de mídia ou instabilidade no cabo de dados."],
                    risks="Pode evoluir para setores pendentes ou não corrigíveis.",
                    recommendation="Monitorar evolução no Módulo de Saúde SMART (Etapa 4).",
                )
            )

        # 11. Possíveis Problemas de Integridade Física / SMART (Cenário 12)
        if device.smart_info.alerts and not device.is_no_media:
            findings.append(
                DiagnosticFinding(
                    code="SMART_INTEGRITY_ALERT",
                    title="Alerta de Integridade Física (SMART)",
                    severity=device.smart_info.status_label,
                    diagnosis="; ".join(device.smart_info.alerts),
                    meaning=(
                        "A telemetria interna do firmware do disco reportou indicadores físicos fora do padrão "
                        "(setores realocados, pendentes, desgaste elevado ou temperatura excessiva)."
                    ),
                    possible_causes=[
                        "Degradação física natural por tempo de uso (Power-On Hours) ou ciclos de escrita.",
                        "Impacto mecânico (em HDs mecânicos) ou superaquecimento.",
                    ],
                    risks="Risco elevado de falha súbita do dispositivo e perda irreversível de dados.",
                    recommendation=(
                        "Priorizar a cópia imediata dos dados (nunca executar CHKDSK /r em disco com Bad Blocks "
                        "físicos crescentes, pois o estresse mecânico pode acelerar a parada total)."
                    ),
                )
            )

        # 12. Caso nenhum problema seja detectado, emite laudo positivo fundamentado
        if not findings:
            smart_note = (
                "Telemetria SMART verificada sem anomalias."
                if device.smart_info.supported
                else "Nota: Contadores SMART profundos indisponíveis sem privilégio de Administrador ou via ponte USB; "
                "a estrutura lógica de partições e volumes encontra-se íntegra."
            )
            findings.append(
                DiagnosticFinding(
                    code="DEVICE_HEALTHY_LOGICAL",
                    title="Estrutura Lógica e Operacional Íntegra",
                    severity=HealthStatus.NORMAL,
                    diagnosis=(
                        f"O dispositivo encontra-se Online, com tabela de partições {device.partition_style} "
                        f"e volumes acessíveis ({device.file_systems_summary})."
                    ),
                    meaning=f"Nenhuma anomalia lógica ou de montagem foi encontrada na varredura Nível 1. {smart_note}",
                    possible_causes=["Dispositivo operando dentro dos parâmetros normais de leitura e montagem."],
                    risks="Nenhum risco imediato identificado.",
                    recommendation=(
                        "Nenhuma intervenção de reparo necessária. Para certificação física completa de bancada, "
                        "consulte o Módulo SMART (Etapa 4) ou Testes de Leitura (Etapa 7)."
                    ),
                )
            )

        # Determina a severidade global do laudo a partir da pior constatação
        severities = [f.severity for f in findings]
        if HealthStatus.CRITICAL in severities:
            overall = HealthStatus.CRITICAL
        elif HealthStatus.WARNING in severities:
            overall = HealthStatus.WARNING
        elif HealthStatus.NORMAL in severities:
            overall = HealthStatus.NORMAL
        else:
            overall = HealthStatus.UNKNOWN

        return DeviceDiagnosticReport(
            device=device,
            overall_status=overall,
            findings=findings,
        )

    def scan_usb_bus_and_ghost_devices(self, simulation_mode: bool = False) -> Tuple[List[UsbBusDiagnosticItem], Dict[int, List[str]]]:
        """
        Inspeciona em modo 100% Somente Leitura o Registro PnP do Windows (winreg instantâneo < 5ms)
        e o Log de Eventos do Sistema para identificar:
        1. Dispositivos USB que falharam na enumeração ('VID_0000&PID_0002' - Falha de Descritor)
           e por isso NÃO aparecem no 'list disk' do DiskPart!
        2. Pendrives / SSDs USB registrados no histórico USBSTOR que não estão montados no momento.
        3. Eventos de erro de E/S do driver 'disk' (Event ID 153 / 7 / 51) indicando falha de leitura LBA.
        """
        if simulation_mode:
            return self._get_simulated_usb_bus_items()

        items: List[UsbBusDiagnosticItem] = []
        io_events_by_disk: Dict[int, List[str]] = {}

        if os.name != "nt":
            return items, io_events_by_disk

        # 1. Leitura instantânea via winreg de dispositivos ativos no USBSTOR\Enum
        active_usbstor_ids = set()
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Services\USBSTOR\Enum",
                0,
                winreg.KEY_READ,
            ) as k_enum:
                cnt, _ = winreg.QueryValueEx(k_enum, "Count")
                for i in range(int(cnt)):
                    val, _ = winreg.QueryValueEx(k_enum, str(i))
                    # Extrai o serial/instância final
                    parts = str(val).split("\\")
                    if parts:
                        active_usbstor_ids.add(parts[-1].upper())
        except OSError:
            pass

        # 2. Verifica falhas de descritor USB (VID_0000&PID_0002 / PID_0001) no Registro PnP
        for pid_err in ("VID_0000&PID_0002", "VID_0000&PID_0001"):
            try:
                key_path = rf"SYSTEM\CurrentControlSet\Enum\USB\{pid_err}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ) as k_usb:
                    sub_count = winreg.QueryInfoKey(k_usb)[0]
                    ports: List[str] = []
                    for idx in range(sub_count):
                        ports.append(winreg.EnumKey(k_usb, idx))
                    if ports:
                        items.append(
                            UsbBusDiagnosticItem(
                                category="FALHA_DESCRITOR_USB",
                                name="Dispositivo USB Desconhecido (Falha na Solicitação de Descritor — Código 43)",
                                instance_id=f"USB\\{pid_err} ({len(ports)} porta(s): {', '.join(ports[:4])})",
                                status="Falha de Enumeração USB",
                                last_arrival="Registrado no Controlador USB",
                                last_removal="Não subiu para o DiskPart",
                                severity=HealthStatus.CRITICAL,
                                explanation=(
                                    "O controlador USB da placa-mãe detectou presença elétrica na porta, mas o "
                                    "pendrive/dispositivo falhou ao responder sua identificação básica (Device Descriptor). "
                                    "Quando isso ocorre, o Windows NÃO carrega o driver de disco e o pendrive "
                                    "NÃO aparece no 'list disk'!"
                                ),
                                possible_causes=[
                                    "Contatos internos do pendrive oxidados ou com mau contato nas linhas de dados (D+ / D-).",
                                    "Curto parcial ou falha no controlador interno do pendrive (cristal ou regulador 3.3V).",
                                    "Porta USB do painel frontal com queda de tensão ou cabo interno com folga.",
                                ],
                                recommendation=(
                                    "1. Limpar os 4 contatos internos do pendrive com álcool isopropílico.\n"
                                    "2. Testar em uma porta USB 2.0/3.0 traseira (soldada direto na placa-mãe).\n"
                                    "3. Se o pendrive não der sinal em nenhuma porta traseira nem em outro PC, "
                                    "há falha eletrônica no controlador USB do pendrive ou fusível SMD aberto."
                                ),
                            )
                        )
            except OSError:
                pass

        # 3. Inspeciona histórico USBSTOR para listar pendrives/discos USB conhecidos que estão ausentes
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Enum\USBSTOR",
                0,
                winreg.KEY_READ,
            ) as k_stor:
                dev_classes_count = winreg.QueryInfoKey(k_stor)[0]
                for i in range(dev_classes_count):
                    dev_class_name = winreg.EnumKey(k_stor, i)
                    with winreg.OpenKey(k_stor, dev_class_name, 0, winreg.KEY_READ) as k_dev:
                        inst_count = winreg.QueryInfoKey(k_dev)[0]
                        for j in range(inst_count):
                            inst_name = winreg.EnumKey(k_dev, j)
                            serial_base = inst_name.split("&")[0].upper()
                            if serial_base in active_usbstor_ids:
                                continue  # Já está ativo e visível no inventário principal
                            with winreg.OpenKey(k_dev, inst_name, 0, winreg.KEY_READ) as k_inst:
                                try:
                                    friendly, _ = winreg.QueryValueEx(k_inst, "FriendlyName")
                                except OSError:
                                    friendly = dev_class_name
                                items.append(
                                    UsbBusDiagnosticItem(
                                        category="DISPOSITIVO_DESCONECTADO",
                                        name=str(friendly),
                                        instance_id=f"USBSTOR\\{dev_class_name}\\{inst_name}",
                                        status="Ausente no Barramento Ativo (Fora do list disk)",
                                        last_arrival="Histórico PnP",
                                        last_removal="Inativo no momento",
                                        severity=HealthStatus.WARNING,
                                        explanation=(
                                            f"O dispositivo '{friendly}' possui registro de driver neste Windows, "
                                            "mas no momento NÃO está respondendo eletricamente ao driver USBSTOR. "
                                            "Se este é o pendrive que está espetado na porta USB agora, a controladora "
                                            "dele desarmou ou perdeu comunicação com a porta!"
                                        ),
                                        possible_causes=[
                                            "Controladora do pendrive em proteção/travamento após falha de leitura NAND.",
                                            "Mau contato físico nos 4 pinos do conector USB-A.",
                                            "Queima do fusível/resistor de entrada de +5V do pendrive.",
                                        ],
                                        recommendation=(
                                            "Remova o pendrive da porta atual, aguarde 10 segundos e reconecte em uma "
                                            "porta USB traseira da placa-mãe. Se ainda assim não mudar para 'Ativo', "
                                            "o defeito é eletrônico/físico no próprio pendrive."
                                        ),
                                    )
                                )
        except OSError as exc:
            logger.debug("Aviso ao ler Enum\\USBSTOR: %s", exc)

        # 4. Consulta rápida (< 1.5s) aos últimos eventos de erro de disco e WPD no Event Log do Sistema
        ps_events_script = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$evts = @(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='disk','Microsoft-Windows-WPDClassInstaller','Microsoft-Windows-UserPnp'; StartTime=(Get-Date).AddHours(-12)} -MaxEvents 40 -ErrorAction SilentlyContinue | Where-Object { $_.Id -in @(7, 11, 51, 129, 153, 154, 25089, 20003) } | Select-Object @{N='Time';E={$_.TimeCreated.ToString('dd/MM/yyyy HH:mm:ss')}}, Id, ProviderName, Message)
$evts | ConvertTo-Json -Compress
"""
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps_events_script,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=6,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stdout = (proc.stdout or "").strip()
            if stdout:
                events_raw = json.loads(stdout)
                if isinstance(events_raw, dict):
                    events_raw = [events_raw]

                # Agrupa eventos repetidos por (Id, Mensagem) para exibição limpa
                grouped_events: Dict[Tuple[int, str], Dict[str, Any]] = {}
                for ev in events_raw:
                    msg = str(ev.get("Message") or "").strip().replace("\r\n", " ")
                    time_str = str(ev.get("Time") or "")
                    ev_id = int(ev.get("Id") or 0)
                    provider = str(ev.get("ProviderName") or "disk")

                    m_disk = re.search(r"Disco\s+(\d+)|Disk\s+(\d+)|Harddisk(\d+)", msg, re.IGNORECASE)
                    if m_disk:
                        d_num = int(m_disk.group(1) or m_disk.group(2) or m_disk.group(3))
                        io_events_by_disk.setdefault(d_num, []).append(f"[{time_str} Evento {ev_id}] {msg}")

                    key = (ev_id, msg)
                    if key not in grouped_events:
                        grouped_events[key] = {
                            "count": 1,
                            "time": time_str,
                            "id": ev_id,
                            "provider": provider,
                            "msg": msg,
                        }
                    else:
                        grouped_events[key]["count"] += 1

                for info in grouped_events.values():
                    cnt = info["count"]
                    ev_id = info["id"]
                    msg = info["msg"]
                    time_str = info["time"]
                    count_badge = f" ({cnt}x ocorrências)" if cnt > 1 else ""

                    sev = HealthStatus.CRITICAL if ev_id in (51, 7, 25089) else HealthStatus.WARNING
                    items.append(
                        UsbBusDiagnosticItem(
                            category="ERRO_IO_DISCO",
                            name=f"Evento de Kernel #{ev_id}{count_badge} ({info['provider']})",
                            instance_id=f"EventID:{ev_id}",
                            status="Falha de Comunicação / E/S",
                            last_arrival=time_str,
                            last_removal="Desarme / Falha de Acesso",
                            severity=sev,
                            explanation=msg,
                            possible_causes=[
                                "O pendrive/disco conectou brevemente (ex: Harddisk3), mas falhou ao ler os setores iniciais e desarmou.",
                                "Memória NAND do pendrive em curto/degradada ou controlador entrando em proteção.",
                                "Queda de tensão ou mau contato na porta USB.",
                            ],
                            recommendation=(
                                "Se o dispositivo citado (ex: Harddisk3 / SanDisk Cruzer Blade) sumiu do 'list disk' "
                                "logo após esses erros, a controladora USB dele desarmou por falha de leitura na memória NAND."
                            ),
                        )
                    )
        except Exception as exc:
            logger.debug("Aviso ao ler eventos de disco do Kernel: %s", exc)

        return items, io_events_by_disk

    @staticmethod
    def _get_simulated_usb_bus_items() -> Tuple[List[UsbBusDiagnosticItem], Dict[int, List[str]]]:
        """Retorna itens simulados de falha de barramento USB e eventos de E/S para testes."""
        sim_items = [
            UsbBusDiagnosticItem(
                category="FALHA_DESCRITOR_USB",
                name="Dispositivo USB Desconhecido (Falha na Solicitação de Descritor de Dispositivo)",
                instance_id=r"USB\VID_0000&PID_0002\6&2991393F&1&4",
                status="Erro (Código 43)",
                last_arrival="01/11/2026 19:40:00",
                last_removal="—",
                severity=HealthStatus.CRITICAL,
                explanation=(
                    "O controlador USB detectou consumo/presença na porta, mas o pendrive não enviou "
                    "o descritor USB (VID/PID). Por isso não aparece no 'list disk' do DiskPart."
                ),
                possible_causes=[
                    "Falha no controlador USB interno do pendrive.",
                    "Mau contato nas linhas de dados D+/D-.",
                ],
                recommendation="Limpar contatos com álcool isopropílico e testar em porta USB traseira.",
            ),
            UsbBusDiagnosticItem(
                category="ERRO_IO_DISCO",
                name="Evento de Kernel #153 (disk)",
                instance_id="EventID:153",
                status="Alerta de E/S",
                last_arrival="01/11/2026 17:40:19",
                last_removal="—",
                severity=HealthStatus.WARNING,
                explanation="A operação de E/S no endereço de bloco lógico 0x0 para o Disco 2 foi repetida.",
                possible_causes=["Timeout de leitura no adaptador USB ou setor inicial instável."],
                recommendation="Testar outro adaptador SATA/USB ou porta traseira.",
            ),
        ]
        return sim_items, {2: ["[Simulação Evento 153] A operação de E/S no bloco lógico 0x0 para o Disco 2 foi repetida."]}
