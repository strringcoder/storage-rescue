# 🛡️ Storage Rescue

**Aplicativo Desktop Windows em Python para Diagnóstico, Recuperação Lógica e Manutenção de HDs, SSDs e Dispositivos USB.**

---

## 1. Visão Geral

O **Storage Rescue** foi desenvolvido para técnicos de informática e profissionais de suporte de bancada no Windows 10 e Windows 11. Seu objetivo é unificar procedimentos técnicos de diagnóstico e manutenção de dispositivos de armazenamento (HDs SATA/USB, SSDs SATA/NVMe, Pendrives, Cartões SD e Adaptadores USB) em uma interface gráfica moderna, organizada e governada por **3 níveis rigorosos de segurança**.

---

## 2. Arquitetura Modular do Projeto

```text
storage_rescue/
├── main.py                      # Ponto de entrada (GUI PySide6 e modo CLI somente leitura)
├── requirements.txt             # Dependências do projeto
├── README.md                    # Documentação técnica e guia de uso
│
├── interface/                   # Camada de Interface Gráfica (PySide6)
│   ├── theme.py                 # Paleta semântica (Verde, Amarelo, Vermelho, Cinza) e QSS Dark
│   ├── main_window.py           # Janela principal com navegação e QThread assíncrona
│   ├── dashboard.py             # Dashboard (5 KPIs + Cards Visuais + Tabela de 11 atributos)
│   ├── devices.py               # Inspeção detalhada de partições, volumes e identidade composta
│   ├── diagnostics.py           # Módulo de Diagnóstico (Etapa 2)
│   ├── recovery.py              # Módulo de Recuperação Lógica (Etapa 5)
│   ├── formatting.py            # Módulo de Preparação e Formatação Segura (Etapa 6)
│   └── reports.py               # Módulo de Histórico e Relatórios (Etapa 3)
│
├── core/                        # Camada de Regras de Negócio e Hardware
│   ├── models.py                # Dataclasses tipadas (DiskDevice, PartitionInfo, SmartSummary)
│   ├── logger.py                # Sistema de logs rotativos em logs/storage_rescue.log
│   ├── disk_manager.py          # Coleta unificada somente leitura (WMI + CIM Storage API)
│   ├── partition_manager.py     # Mapeamento de partições GPT/MBR/RAW e volumes
│   ├── smart_manager.py         # Telemetria SMART (smartctl + StorageReliabilityCounter)
│   ├── usb_manager.py           # Detecção de pontes USB, 0 bytes e No Media
│   ├── health_check.py          # Motor de classificação de integridade e alertas
│   └── device_identity.py       # Assinatura composta (Modelo + Serial + Capacidade)
│
├── database/                    # Camada de Persistência Local (SQLite)
│   ├── database.py              # Conexão e inicialização de tabelas
│   └── history.py               # Consulta e registro de diagnósticos
│
├── security/                    # Camada de Segurança Operacional
│   ├── confirmations.py         # Políticas de Nível 1, Nível 2 e Nível 3
│   └── protections.py           # Bloqueio de discos de Boot, Sistema, Paginação e Hibernação
│
├── reports/                     # Diretório de exportação de laudos (TXT / JSON)
├── logs/                        # Diretório de logs detalhados da aplicação
└── tests/                       # Testes automatizados e simulados
    └── test_etapa1_inventory.py # Testes de unidade e interface da Etapa 1
```

---

## 3. Como Executar

### 3.1. Instalar Dependências
```powershell
pip install -r requirements.txt
```

### 3.2. Iniciar a Interface Gráfica (Modo Somente Leitura Real)
```powershell
python main.py
```

### 3.3. Iniciar em Modo Simulação de Bancada (Dispositivos de Teste)
```powershell
python main.py --simulate
```

### 3.4. Executar Inventário Rápido no Terminal (CLI Somente Leitura)
```powershell
python main.py --cli-inventory
```

### 3.5. Executar Testes Automatizados
```powershell
python -m unittest discover -s tests -v
```

---

## 4. Status das Etapas de Desenvolvimento

- [x] **Etapa 1**: Criar a interface principal (Dashboard) e inventário somente leitura dos discos.
- [ ] **Etapa 2**: Implementar diagnóstico completo em modo somente leitura.
- [ ] **Etapa 3**: Implementar histórico SQLite e exportação de relatórios (TXT, JSON e Ficha Técnica).
- [ ] **Etapa 4**: Implementar módulo dedicado de saúde SMART detalhada.
- [ ] **Etapa 5**: Implementar recuperação lógica não destrutiva (Nível 2).
- [ ] **Etapa 6**: Implementar preparação e formatação segura em 8 passos (Nível 3).
- [ ] **Etapa 7**: Implementar testes de integridade e verificação de capacidade real.
- [ ] **Etapa 8**: Criar executável Windows com PyInstaller.
