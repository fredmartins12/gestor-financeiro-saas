document.addEventListener('DOMContentLoaded', () => {
    // --- ESTADO GLOBAL DA APLICAÇÃO ---
    let allAccounts = [];
    let activeOperations = [];
    let transactionHistory = [];

    // --- SELETORES DE ELEMENTOS DO DOM ---
    const modals = {
        account: setupModal(document.getElementById('account-modal')),
        transaction: setupModal(document.getElementById('transaction-modal')),
        expense: setupModal(document.getElementById('expense-modal')),
        transfer: setupModal(document.getElementById('transfer-modal')),
        report: setupModal(document.getElementById('report-modal')),
        resolve: setupModal(document.getElementById('resolve-modal')),
    };

    const addAccountBtn = document.getElementById('add-account-btn');
    const addTransactionBtn = document.getElementById('add-transaction-btn');
    const addExpenseBtn = document.getElementById('add-expense-btn');
    const transferBtn = document.getElementById('transfer-btn');
    const reportBtn = document.getElementById('report-btn');
    const backupBtn = document.getElementById('backup-btn');

    const accountForm = document.getElementById('account-form');
    const transactionForm = document.getElementById('transaction-form');
    const expenseForm = document.getElementById('expense-form');
    const transferForm = document.getElementById('transfer-form');
    const operationForm = document.getElementById('operation-form');
    const resolveForm = document.getElementById('resolve-form');
    
    const operationCategorySelect = document.getElementById('operation-category');
    const legsContainer = document.getElementById('legs-container');
    const addLegBtn = document.getElementById('add-leg-btn');
    const activeOperationsContainer = document.getElementById('active-operations-container');
    const mainTabsContainer = document.getElementById('main-tabs-container');
    const mainContainer = document.querySelector('.max-w-screen-xl');


    // --- SELETORES E LÓGICA PARA FERRAMENTAS DE DADOS ---
    const restoreFileInput = document.getElementById('restore-file-input');
    const restoreBtn = document.getElementById('restore-btn');
    const csvFileInput = document.getElementById('csv-file-input');
    const importCsvBtn = document.getElementById('import-csv-btn');
    const downloadTemplateBtn = document.getElementById('download-template-btn');

    // Habilita/desabilita botão de restaurar
    restoreFileInput.addEventListener('change', () => {
        restoreBtn.disabled = !restoreFileInput.files.length;
    });

    // Habilita/desabilita botão de importar CSV
    csvFileInput.addEventListener('change', () => {
        importCsvBtn.disabled = !csvFileInput.files.length;
    });

    // Ação do botão de restaurar
    restoreBtn.addEventListener('click', async () => {
        if (!restoreFileInput.files.length) {
            return showToast('Por favor, selecione um arquivo de backup.', 'error');
        }
        if (!confirm('ATENÇÃO!\n\nEsta ação irá apagar TODOS os seus dados atuais e substituí-los pelos dados do backup.\n\nEsta ação não pode ser desfeita. Deseja continuar?')) {
            return;
        }

        const file = restoreFileInput.files[0];
        const formData = new FormData();
        formData.append('backupFile', file);

        try {
            restoreBtn.innerHTML = '<div class="spinner mx-auto"></div>';
            restoreBtn.disabled = true;

            const response = await fetch('/api/restore', { method: 'POST', body: formData });
            const result = await response.json();

            if (!response.ok) throw new Error(result.error);

            showToast(result.message, 'success');
            initializeApp(); // Recarrega o app
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            restoreFileInput.value = ''; 
            restoreBtn.innerHTML = 'Restaurar Dados';
            restoreBtn.disabled = true;
        }
    });

    // Ação do botão de importar CSV
    importCsvBtn.addEventListener('click', async () => {
        if (!csvFileInput.files.length) {
            return showToast('Por favor, selecione um arquivo CSV.', 'error');
        }

        const file = csvFileInput.files[0];
        const formData = new FormData();
        formData.append('csvFile', file);

        try {
            importCsvBtn.innerHTML = '<div class="spinner mx-auto"></div>';
            importCsvBtn.disabled = true;
            
            const response = await fetch('/api/import-csv', { method: 'POST', body: formData });
            const result = await response.json();

            if (!response.ok) throw new Error(result.error);
            
            showToast(result.message, 'success');
            initializeApp(); // Recarrega o app
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            csvFileInput.value = '';
            importCsvBtn.innerHTML = 'Importar CSV';
            importCsvBtn.disabled = true;
        }
    });

    // Ação do botão de baixar modelo
    downloadTemplateBtn.addEventListener('click', () => {
        window.location.href = '/api/csv-template';
    });


    // --- FUNÇÕES DE API ---
    async function apiRequest(endpoint, method = 'GET', body = null) {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json'
            }
        };
        if (body) options.body = JSON.stringify(body);

        const response = await fetch(endpoint, options);
        
        // Tentativa de pegar o JSON, mesmo em caso de erro
        let errorData = null;
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
             errorData = await response.json().catch(() => null);
        } else if (!response.ok) {
            // Se o erro não for JSON (como o erro que estava ocorrendo), tenta pegar como texto
            const errorText = await response.text().catch(() => 'Resposta vazia');
            // Retorna a falha original que estava sendo capturada pelo catch externo
            throw new Error(`O servidor retornou um erro não-JSON. Status: ${response.status}. Conteúdo: ${errorText.substring(0, 100)}...`);
        }

        if (!response.ok) {
            throw new Error((errorData && errorData.error) || `HTTP error! status: ${response.status}`);
        }
        
        // Se for sucesso, retorna o JSON se houver
        if (contentType && contentType.includes("application/json")) {
            return errorData || { message: 'Success' };
        } else {
             return { message: 'Success' };
        }
    }

    // --- FUNÇÕES DE UI E UTILITÁRIOS ---
    const formatCurrency = (value) => `R$ ${(typeof value === 'number' ? value : 0).toFixed(2).replace('.', ',').replace('-', '-R$ ')}`;
    const formatPercent = (value) => `${(typeof value === 'number' ? value : 0).toFixed(2).replace('.', ',')}%`;
    const floorToTwoDecimals = (num) => {
        const numAsFloat = parseFloat(num);
        if (isNaN(numAsFloat)) return 0;
        return Math.floor(numAsFloat * 100) / 100;
    };

    function showToast(message, type = 'success') {
        const toastContainer = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    function setupModal(modalElement) {
        const controller = {
            element: modalElement,
            open: () => modalElement.classList.add('flex'),
            close: () => modalElement.classList.remove('flex'),
        };
        modalElement.addEventListener('click', (e) => {
            if (e.target === modalElement || e.target.closest('.cancel-modal-btn')) {
                 controller.close();
                 // Reset forms ao fechar
                 const form = modalElement.querySelector('form');
                 if (form) form.reset();
            }
        });
        return controller;
    }

    function populateAccountSelect(selectElement, includePlaceholder = true, filterId = null) {
        selectElement.innerHTML = includePlaceholder ? '<option value="">Selecione...</option>' : '';
        const optionsHtml = allAccounts
            .filter(acc => acc.ativa && (filterId === null || acc.id != filterId))
            .map(acc => `<option value="${acc.id}" data-freebet-balance="${acc.saldo_freebets}">${acc.nome} (${formatCurrency(acc.saldo)})</option>`)
            .join('');
        selectElement.innerHTML += optionsHtml;
    }

    function getAccountOptionsHtml() {
         return allAccounts
            .filter(acc => acc.ativa)
            .map(acc => `<option value="${acc.id}" data-freebet-balance="${acc.saldo_freebets}">${acc.nome} (${formatCurrency(acc.saldo)})</option>`)
            .join('');
    }

    // --- RENDERIZAÇÃO ---
    function renderTables() {
        const providers = ['bet365', 'betesporte', 'betano', 'sportingbet', 'pessoal'];
        providers.forEach(provider => {
            const tableBodyId = provider === 'pessoal' ? 'personal-accounts-body' : `${provider}-accounts-body`;
            const tableBody = document.getElementById(tableBodyId);
            if (!tableBody) return;

            const filteredAccounts = allAccounts.filter(acc => acc.casa_de_aposta === provider);
            
            tableBody.innerHTML = filteredAccounts.length === 0
                ? `<tr><td colspan="8" class="text-center p-4">Nenhuma conta encontrada.</td></tr>`
                : filteredAccounts.map(acc => {
                    let statusHtml = '';

                    // Tag de Depósito (Apostas)
                    if (acc.saldo < 150 && provider !== 'pessoal') {
                        statusHtml = `<span class="status-tag tag-deposit">💰 Depósito</span>`;
                    }

                    // Aviso de Código
                    if (acc.data_ultimo_codigo) {
                        const today = new Date();
                        today.setHours(0, 0, 0, 0);
                        const lastCodeDate = new Date(acc.data_ultimo_codigo + 'T00:00:00');
                        const diffTime = today - lastCodeDate;
                        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                        
                        if (diffDays === 6) {
                            statusHtml += `<span class="ml-2" title="A conta '${acc.nome}' precisará de código amanhã!">⚠️</span>`;
                        } else if (diffDays >= 7) {
                             statusHtml += `<span class="ml-2" title="A conta '${acc.nome}' precisa de um novo código!">🚨</span>`;
                        }
                    }

                    // Status de Pagamento de Clube
                    let paymentHtml = 'N/A';
                    if (acc.dia_pagamento && provider !== 'pessoal') {
                        const today = new Date();
                        const currentYear = today.getFullYear();
                        const currentMonth = today.getMonth(); // 0-11
                        const currentPeriod = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
                        const dueDateThisMonth = new Date(currentYear, currentMonth, acc.dia_pagamento);
                        
                        if (acc.ultimo_periodo_pago === currentPeriod) {
                            // Pago
                            const nextDueDate = new Date(currentYear, currentMonth + 1, acc.dia_pagamento);
                            const nextDateStr = `${String(nextDueDate.getDate()).padStart(2, '0')}/${String(nextDueDate.getMonth() + 1).padStart(2, '0')}`;
                            paymentHtml = `<span class="status-tag tag-paid">Pago ✔ (Próximo: ${nextDateStr})</span>`;
                        } else {
                            // Pendente ou Vencido
                            const diffTime = dueDateThisMonth.getTime() - today.getTime();
                            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                            const dueDateStr = `${String(dueDateThisMonth.getDate()).padStart(2, '0')}/${String(dueDateThisMonth.getMonth() + 1).padStart(2, '0')}`;
                            
                            if (diffDays < 0) {
                                paymentHtml = `<span class="status-tag tag-overdue">${dueDateStr} (Vencido há ${Math.abs(diffDays)} dias)</span>`;
                            } else {
                                paymentHtml = `<span class="status-tag tag-due">${dueDateStr} (Vence em ${diffDays} dias)</span>`;
                            }
                            paymentHtml += `<span class="pay-btn" data-account-id="${acc.id}" data-account-name="${acc.nome}">Pagar</span>`;
                        }
                    }

                    return `
                        <tr class="bg-white border-b hover:bg-gray-50" data-account-id="${acc.id}">
                            ${provider !== 'pessoal' ? `<td class="px-6 py-4">${statusHtml}</td>` : ''}
                            <td class="px-6 py-4 font-medium text-gray-900">${acc.nome}</td>
                            <td class="px-6 py-4 font-bold">${formatCurrency(acc.saldo)}</td>
                            <td class="px-6 py-4 font-medium text-blue-600">${formatCurrency(acc.saldo_freebets)}</td>
                            ${provider !== 'pessoal' ? `<td class="px-6 py-4">${formatCurrency(acc.volume_clube)}</td>` : ''}
                            <td class="px-6 py-4 text-sm">${paymentHtml}</td>
                            <td class="px-6 py-4">${acc.observacoes || ''}</td>
                            <td class="px-6 py-4 flex flex-wrap gap-x-4 gap-y-2 items-center">
                                <span class="action-btn edit-btn" data-id="${acc.id}">Editar</span>
                                <span class="action-btn delete-btn" data-id="${acc.id}">Excluir</span>
                            </td>
                        </tr>
                    `;
                }).join('');
        });
    }

    function renderActiveOperations() {
        if (activeOperations.length === 0) {
            activeOperationsContainer.innerHTML = `<p class="text-gray-500 bg-white shadow-md rounded-lg p-6">Nenhuma operação ativa no momento.</p>`;
            return;
        }

        // Agrupa as apostas por operationId
        const opsById = activeOperations.reduce((acc, bet) => {
            const details = bet.detalhes;
            const opId = details.operationId;
            if (!acc[opId]) {
                acc[opId] = {
                    gameName: bet.descricao.split(' - ')[0],
                    totalStake: 0,
                    bets: []
                };
            }
            acc[opId].bets.push({ ...bet, detalhes: details });
            acc[opId].totalStake += Math.abs(bet.valor);
            return acc;
        }, {});

        activeOperationsContainer.innerHTML = Object.entries(opsById).map(([opId, data]) => {
            const isMultiBet = data.bets.length > 1;
            const toggleId = `toggle-${opId}`;

            const detailRows = data.bets.map(bet => {
                const isFreeBet = bet.tipo === 'freebet_placed';
                return `
                    <tr class="text-sm border-t border-gray-100">
                        <td class="px-4 py-2 text-gray-500">${bet.nome_conta}</td>
                        <td class="px-4 py-2">${isFreeBet ? 'Freebet' : 'Dinheiro'}</td>
                        <td class="px-4 py-2">${formatCurrency(Math.abs(bet.valor))}</td>
                        <td class="px-4 py-2">${bet.detalhes.odd}</td>
                        <td class="px-4 py-2">${bet.detalhes.matchId || 'N/A'}</td>
                    </tr>
                `;
            }).join('');

            return `
                <div class="bg-white shadow-lg rounded-xl mb-4 p-4 transition duration-300 ease-in-out">
                    <div class="flex justify-between items-center cursor-pointer" data-toggle-id="${toggleId}">
                        <div>
                            <p class="text-lg font-bold text-gray-800">${data.gameName}</p>
                            <p class="text-sm text-gray-500">${isMultiBet ? `Multi Aposta (${data.bets.length} pernas)` : `Aposta Simples`}</p>
                        </div>
                        <div class="flex items-center gap-4">
                            <span class="text-xl font-bold text-red-600">${formatCurrency(data.totalStake)}</span>
                            <button class="bg-green-500 text-white py-1 px-3 rounded text-sm font-semibold resolve-op-btn" data-operation-id="${opId}">Resolver</button>
                            <svg data-toggle-icon="${toggleId}" class="w-5 h-5 text-gray-500 toggle-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                        </div>
                    </div>
                    
                    <div id="${toggleId}" class="operation-body">
                        <div class="mt-4 p-3 bg-gray-50 rounded-md">
                            <p class="text-sm font-semibold mb-2">Detalhes da Operação (ID: ${opId})</p>
                            <table class="min-w-full">
                                <thead>
                                    <tr class="text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        <th class="px-4 py-2">Conta</th>
                                        <th class="px-4 py-2">Tipo</th>
                                        <th class="px-4 py-2">Valor</th>
                                        <th class="px-4 py-2">Odd</th>
                                        <th class="px-4 py-2">Match ID</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${detailRows}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Adiciona evento de toggle
        document.querySelectorAll('[data-toggle-id]').forEach(el => {
            el.addEventListener('click', (e) => {
                // Não expandir/recolher se clicar nos botões internos
                if (e.target.closest('.resolve-op-btn') || e.target.closest('.action-btn')) return;

                const targetId = el.getAttribute('data-toggle-id');
                const targetEl = document.getElementById(targetId);
                el.parentElement.classList.toggle('is-expanded');
            });
        });
    }

    function renderTransactionHistory() {
        const historyTableBody = document.getElementById('history-table-body');
        if (!historyTableBody) return;

        historyTableBody.innerHTML = transactionHistory.length === 0
            ? `<tr><td colspan="5" class="text-center p-4">Nenhuma transação recente.</td></tr>`
            : transactionHistory.map(t => {
                const date = new Date(t.data_criacao).toLocaleDateString('pt-BR');
                const time = new Date(t.data_criacao).toLocaleTimeString('pt-BR').substring(0, 5);
                const valor = formatCurrency(t.valor);
                
                let colorClass = '';
                if (t.tipo === 'bet_won' || t.tipo === 'deposit' || t.tipo === 'transfer') {
                    colorClass = t.valor > 0 ? 'text-green-600' : 'text-red-600';
                } else if (t.tipo === 'club_payment' || t.tipo === 'expense' || t.tipo === 'withdrawal') {
                    colorClass = 'text-red-600';
                } else if (t.tipo === 'bet_placed' || t.tipo === 'freebet_placed') {
                    colorClass = 'text-yellow-600';
                }

                return `
                    <tr class="bg-white border-b hover:bg-gray-50">
                        <td class="px-6 py-3 text-sm text-gray-500">${date} ${time}</td>
                        <td class="px-6 py-3 font-medium text-gray-900">${t.nome_conta}</td>
                        <td class="px-6 py-3 text-sm uppercase">${t.tipo.replace('_', ' ')}</td>
                        <td class="px-6 py-3 font-semibold ${colorClass}">${valor}</td>
                        <td class="px-6 py-3 text-sm text-gray-700">${t.descricao}</td>
                    </tr>
                `;
            }).join('');
    }

    function updateFinancialSummary(summary) {
        document.getElementById('monthly-credits').textContent = formatCurrency(summary.monthly_credits);
        document.getElementById('monthly-debits').textContent = formatCurrency(summary.monthly_debits);
        
        const netElement = document.getElementById('monthly-net');
        netElement.textContent = formatCurrency(summary.monthly_net);
        netElement.classList.remove('text-green-600', 'text-red-600');
        netElement.classList.add(summary.monthly_net >= 0 ? 'text-green-600' : 'text-red-600');
    }

    // --- LÓGICA DE FORMULÁRIOS E SUBMISSÃO ---
    addAccountBtn.addEventListener('click', () => {
        document.getElementById('modal-title').textContent = 'Cadastrar Nova Conta';
        document.getElementById('account-id').value = '';
        accountForm.reset();
        modals.account.open();
    });

    addTransactionBtn.addEventListener('click', () => {
        populateAccountSelect(document.getElementById('transaction-account'));
        modals.transaction.open();
    });

    addExpenseBtn.addEventListener('click', () => {
         populateAccountSelect(document.getElementById('expense-account'));
         modals.expense.open();
    });

    transferBtn.addEventListener('click', () => {
        populateAccountSelect(document.getElementById('transfer-account-origin'));
        populateAccountSelect(document.getElementById('transfer-account-destination'), true, document.getElementById('transfer-account-origin').value);
        modals.transfer.open();
    });

    // Lógica para atualizar o select de destino ao mudar a origem
    document.getElementById('transfer-account-origin').addEventListener('change', (e) => {
        populateAccountSelect(document.getElementById('transfer-account-destination'), true, e.target.value);
    });
    
    // Abrir Modal de Relatório
    reportBtn.addEventListener('click', async () => {
        try {
            const data = await apiRequest('/api/relatorio');
            renderReport(data);
            modals.report.open();
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Ação do botão de Backup
    backupBtn.addEventListener('click', () => {
         window.location.href = '/api/backup';
    });


    // Delegação de eventos para botões de Editar/Excluir/Pagar
    mainContainer.addEventListener('click', async (e) => {
        // --- EDITAR CONTA ---
        if (e.target.classList.contains('edit-btn')) {
            const id = e.target.getAttribute('data-id');
            const account = allAccounts.find(acc => acc.id == id);
            if (account) {
                document.getElementById('modal-title').textContent = 'Editar Conta';
                document.getElementById('account-id').value = account.id;
                document.getElementById('account-name').value = account.nome;
                document.getElementById('account-provider').value = account.casa_de_aposta;
                document.getElementById('account-balance').value = account.saldo;
                document.getElementById('account-freebet-balance').value = account.saldo_freebets;
                document.getElementById('account-payment-day').value = account.dia_pagamento;
                document.getElementById('account-payment-value').value = account.valor_pagamento;
                document.getElementById('account-goal').value = account.meta;
                document.getElementById('account-club-volume').value = account.volume_clube;
                document.getElementById('account-last-code-date').value = account.data_ultimo_codigo || '';
                document.getElementById('account-obs').value = account.observacoes || '';
                
                // Salvar o último período pago no campo escondido
                const lastPaidInput = document.getElementById('account-last-paid-period');
                if (lastPaidInput) {
                     lastPaidInput.value = account.ultimo_periodo_pago || '';
                }

                modals.account.open();
            }
        } 
        
        // --- DESATIVAR/EXCLUIR CONTA ---
        else if (e.target.classList.contains('delete-btn')) {
            const id = e.target.getAttribute('data-id');
            const account = allAccounts.find(acc => acc.id == id);
            if (account && confirm(`Tem certeza que deseja desativar a conta "${account.nome}"? Ela será movida para o arquivo.`)) {
                try {
                    await apiRequest(`/api/contas/${id}`, 'DELETE');
                    showToast(`Conta ${account.nome} desativada com sucesso.`, 'success');
                    initializeApp();
                } catch (error) {
                    showToast(error.message, 'error');
                }
            }
        } 
        
        // --- PAGAR CLUBE ---
        else if (e.target.classList.contains('pay-btn')) {
            const id = e.target.getAttribute('data-account-id');
            const name = e.target.getAttribute('data-account-name');

            if (confirm(`Confirmar o pagamento do clube para a conta "${name}"?`)) {
                try {
                    await apiRequest(`/api/contas/${id}/pagamento`, 'POST');
                    showToast(`Pagamento do clube para ${name} registrado com sucesso.`, 'success');
                    initializeApp();
                } catch (error) {
                    showToast(error.message, 'error');
                }
            }
        }
        
        // --- RESOLVER OPERAÇÃO ---
        else if (e.target.classList.contains('resolve-op-btn')) {
            const opId = e.target.getAttribute('data-operation-id');
            document.getElementById('resolve-operation-id').value = opId;
            document.getElementById('resolve-modal-title').textContent = `Resolver Operação ID: ${opId}`;
            modals.resolve.open();
        }
    });

    // --- Submissão de Formulários ---
    
    // 1. FORMULÁRIO DE CONTA
    accountForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('account-id').value;
        const submitBtn = e.submitter;
        submitBtn.innerHTML = '<div class="spinner mx-auto"></div>';
        submitBtn.disabled = true;

        const data = {
            nome: document.getElementById('account-name').value,
            casaDeAposta: document.getElementById('account-provider').value,
            saldo: parseFloat(document.getElementById('account-balance').value) || 0,
            saldoFreebets: parseFloat(document.getElementById('account-freebet-balance').value) || 0,
            diaPagamento: parseInt(document.getElementById('account-payment-day').value) || null,
            valorPagamento: parseFloat(document.getElementById('account-payment-value').value) || null,
            meta: parseFloat(document.getElementById('account-goal').value) || 100,
            volumeClube: parseFloat(document.getElementById('account-club-volume').value) || 0,
            dataUltimoCodigo: document.getElementById('account-last-code-date').value || null,
            observacoes: document.getElementById('account-obs').value,
            // Campo escondido para PUT
            ultimoPeriodoPago: document.getElementById('account-last-paid-period')?.value || null 
        };

        try {
            if (id) {
                // PUT (Edição)
                await apiRequest(`/api/contas/${id}`, 'PUT', data);
                showToast('Conta atualizada com sucesso!', 'success');
            } else {
                // POST (Criação)
                await apiRequest('/api/contas', 'POST', data);
                showToast('Conta criada com sucesso!', 'success');
            }
            modals.account.close();
            initializeApp();
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            submitBtn.innerHTML = 'Salvar';
            submitBtn.disabled = false;
        }
    });

    // 2. FORMULÁRIO DE TRANSAÇÃO GENÉRICA (Deposit/Withdrawal)
    transactionForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = e.submitter;
        submitBtn.innerHTML = '<div class="spinner mx-auto"></div>';
        submitBtn.disabled = true;

        const valor = parseFloat(document.getElementById('transaction-value').value);
        if (valor <= 0) {
            showToast('O valor deve ser positivo.', 'error');
            submitBtn.innerHTML = 'Registrar';
            submitBtn.disabled = false;
            return;
        }

        const data = {
            conta_id: parseInt(document.getElementById('transaction-account').value),
            tipo: document.getElementById('transaction-type').value,
            valor: valor,
            descricao: document.getElementById('transaction-description').value,
        };

        try {
            await apiRequest('/api/transacoes/generico', 'POST', data);
            showToast('Transação registrada com sucesso!', 'success');
            modals.transaction.close();
            initializeApp();
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            submitBtn.innerHTML = 'Registrar';
            submitBtn.disabled = false;
        }
    });
    
    // 3. FORMULÁRIO DE DESPESA (Expense)
    expenseForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = e.submitter;
        submitBtn.innerHTML = '<div class="spinner mx-auto"></div>';
        submitBtn.disabled = true;

        const valor = parseFloat(document.getElementById('expense-value').value);
        if (valor <= 0) {
            showToast('O valor deve ser positivo.', 'error');
            submitBtn.innerHTML = 'Registrar';
            submitBtn.disabled = false;
            return;
        }

        const data = {
            conta_id: parseInt(document.getElementById('expense-account').value),
            tipo: 'expense', // Fixo como expense
            valor: valor,
            descricao: document.getElementById('expense-description').value,
        };

        try {
            await apiRequest('/api/transacoes/generico', 'POST', data);
            showToast('Despesa registrada com sucesso!', 'success');
            modals.expense.close();
            initializeApp();
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            submitBtn.innerHTML = 'Registrar Despesa';
            submitBtn.disabled = false;
        }
    });

    // 4. FORMULÁRIO DE TRANSFERÊNCIA
    transferForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = e.submitter;
        submitBtn.innerHTML = '<div class="spinner mx-auto"></div>';
        submitBtn.disabled = true;

        const data = {
            conta_origem_id: parseInt(document.getElementById('transfer-account-origin').value),
            conta_destino_id: parseInt(document.getElementById('transfer-account-destination').value),
            valor: parseFloat(document.getElementById('transfer-value').value),
            descricao: document.getElementById('transfer-description').value,
        };
        
        if (data.conta_origem_id === data.conta_destino_id) {
             showToast('Conta de origem e destino devem ser diferentes.', 'error');
             submitBtn.innerHTML = 'Transferir';
             submitBtn.disabled = false;
             return;
        }

        try {
            await apiRequest('/api/transferencia', 'POST', data);
            showToast('Transferência realizada com sucesso!', 'success');
            modals.transfer.close();
            initializeApp();
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            submitBtn.innerHTML = 'Transferir';
            submitBtn.disabled = false;
        }
    });

    // 5. FORMULÁRIO DE OPERAÇÃO (Aposta/Freebet)
    // Gerenciamento de Múltiplas Pernas
    function addLegRow(isFreeBet = false, legData = {}) {
        const id = Date.now();
        const newLeg = document.createElement('div');
        newLeg.className = 'leg-container grid grid-cols-1 md:grid-cols-6 gap-2 border-b pb-3';
        newLeg.innerHTML = `
            <div class="col-span-2">
                <label class="block text-sm font-medium text-gray-700">Conta/Tipo</label>
                <select id="leg-account-${id}" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm bet-account" required>
                    <option value="">Selecione a conta...</option>
                    ${getAccountOptionsHtml()}
                </select>
                <select id="leg-type-${id}" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm bet-type ${isFreeBet ? 'hidden' : ''}" ${isFreeBet ? '' : 'required'}>
                    <option value="bet" ${legData.type === 'bet' ? 'selected' : ''}>Dinheiro</option>
                    <option value="freebet" ${legData.type === 'freebet' ? 'selected' : ''}>Freebet</option>
                </select>
                <input type="hidden" id="leg-is-freebet-${id}" value="${isFreeBet}">
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700">Valor (R$)</label>
                <input type="number" id="leg-value-${id}" step="0.01" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm bet-value" value="${legData.value || ''}" required>
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700">Odd</label>
                <input type="number" id="leg-odd-${id}" step="0.01" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm bet-odd" value="${legData.odd || ''}" required>
            </div>
            <div class="col-span-1">
                <label class="block text-sm font-medium text-gray-700">G. Potencial</label>
                <p id="leg-potential-return-${id}" class="mt-1 block w-full text-lg font-bold text-gray-800 leg-potential">0,00</p>
            </div>
            <div class="col-span-1 flex items-end">
                <button type="button" class="bg-red-500 text-white p-2 rounded-md hover:bg-red-600 remove-leg-btn w-full" data-leg-id="${id}">Remover</button>
            </div>
        `;
        legsContainer.appendChild(newLeg);

        // Define valores iniciais e adiciona listeners
        const legAccountSelect = newLeg.querySelector(`#leg-account-${id}`);
        const legValueInput = newLeg.querySelector(`#leg-value-${id}`);
        const legOddInput = newLeg.querySelector(`#leg-odd-${id}`);
        const legTypeSelect = newLeg.querySelector(`#leg-type-${id}`);

        if (legData.accountId) legAccountSelect.value = legData.accountId;

        const updateHandler = () => updateLegSummary(newLeg);
        
        legAccountSelect.addEventListener('change', updateHandler);
        legValueInput.addEventListener('input', updateHandler);
        legOddInput.addEventListener('input', updateHandler);
        
        if (!isFreeBet) {
             legTypeSelect.addEventListener('change', (e) => {
                 const isFb = e.target.value === 'freebet';
                 if (isFb) {
                     // Freebet usa o saldo de freebet, ignora aposta maior que o valor da freebet
                     legValueInput.required = false; 
                     legValueInput.setAttribute('max', legAccountSelect.querySelector(`option[value="${legAccountSelect.value}"]`).dataset.freebetBalance);
                 } else {
                     legValueInput.required = true;
                     legValueInput.removeAttribute('max');
                 }
                 updateHandler();
             });
        }
        
        updateHandler();
    }

    function updateLegSummary(legEl) {
        const value = parseFloat(legEl.querySelector('.bet-value').value) || 0;
        const odd = parseFloat(legEl.querySelector('.bet-odd').value) || 0;
        const isFreeBetInput = legEl.querySelector('.bet-type')?.value === 'freebet' || legEl.querySelector('#leg-is-freebet-')?.value === 'true';

        let potentialReturn = 0;
        if (value > 0 && odd > 1) {
            if (isFreeBetInput) {
                // Freebet: Retorno = (Odd * Stake) - Stake
                potentialReturn = (odd * value) - value;
            } else {
                // Aposta normal: Retorno = Odd * Stake
                potentialReturn = odd * value;
            }
        }
        
        // Garante que o potencial de retorno não seja negativo se a odd for 1.00 ou 0
        potentialReturn = Math.max(0, potentialReturn);

        legEl.querySelector('.leg-potential').textContent = formatCurrency(potentialReturn);
        
        // Chama o resumo total após atualizar o resumo desta perna
        updateTotalOperationSummary();
    }

    function updateTotalOperationSummary() {
        let totalStake = 0;
        let totalPotentialReturn = 0;
        let totalFreebetStake = 0;
        let totalNormalStake = 0;

        legsContainer.querySelectorAll('.leg-container').forEach(legEl => {
            const value = parseFloat(legEl.querySelector('.bet-value').value) || 0;
            const potentialReturnText = legEl.querySelector('.leg-potential').textContent;
            
            // Extrai o valor numérico do retorno potencial formatado
            const potentialReturn = parseFloat(potentialReturnText.replace('R$', '').replace('.', '').replace(',', '.').trim().replace('-', '')) || 0;
            
            // O valor da aposta (stake) contribui para o total apostado
            totalStake += value; 
            
            // Apenas o lucro potencial (retorno total - stake original) é somado para o total potencial
            // Se for Freebet, o potencial já é o lucro líquido. Se for aposta normal, o potencial é o ganho total.
            // Para Freebet, o potencial já está calculado líquido na função updateLegSummary
            totalPotentialReturn += potentialReturn;
            
            // Separa os stakes por tipo para exibição
            const isFreeBetInput = legEl.querySelector('.bet-type')?.value === 'freebet' || legEl.querySelector('#leg-is-freebet-')?.value === 'true';
            if (isFreeBetInput) {
                totalFreebetStake += value;
            } else {
                totalNormalStake += value;
            }
        });

        document.getElementById('total-stake').textContent = formatCurrency(totalStake);
        document.getElementById('total-potential-return').textContent = formatCurrency(totalPotentialReturn);
        document.getElementById('total-freebet-stake').textContent = formatCurrency(totalFreebetStake);
        document.getElementById('total-normal-stake').textContent = formatCurrency(totalNormalStake);
    }

    addLegBtn.addEventListener('click', () => addLegRow());
    legsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-leg-btn')) {
            if (legsContainer.querySelectorAll('.leg-container').length > 1) {
                e.target.closest('.leg-container').remove();
                updateTotalOperationSummary();
            } else {
                 showToast('Pelo menos uma perna é necessária.', 'error');
            }
        }
    });

    operationForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = e.submitter;
        submitBtn.innerHTML = '<div class="spinner mx-auto"></div>';
        submitBtn.disabled = true;

        // Gerar um Operation ID único (timestamp)
        const operationId = Date.now().toString();
        const category = document.getElementById('operation-category').value;
        const gameName = document.getElementById('operation-game').value;

        let totalBets = [];
        let success = true;

        if (category === 'cassino') {
            // Lógica para Cassino
            const accountId = parseInt(document.getElementById('cassino-account').value);
            const value = parseFloat(document.getElementById('cassino-value').value);
            const type = document.getElementById('cassino-type').value; // bet_placed ou freebet_placed

            if (value <= 0) {
                 showToast('O valor da aposta deve ser positivo.', 'error');
                 success = false;
            } else {
                totalBets.push({
                    conta_id: accountId,
                    tipo: type, 
                    valor: value, 
                    descricao: `${gameName} - Cassino`,
                    detalhes: {
                        operationId: operationId,
                        gameName: gameName,
                        category: 'cassino',
                        type: 'simples',
                        status: 'ativa',
                        matchId: document.getElementById('cassino-match-id').value || null,
                        odd: parseFloat(document.getElementById('cassino-odd').value) || 0,
                    }
                });
            }

        } else {
             // Lógica para Esportes (Múltiplas Pernas)
            legsContainer.querySelectorAll('.leg-container').forEach(legEl => {
                const accountId = parseInt(legEl.querySelector('.bet-account').value);
                const typeSelect = legEl.querySelector('.bet-type');
                const isFreeBetInput = typeSelect ? typeSelect.value === 'freebet' : legEl.querySelector('#leg-is-freebet-')?.value === 'true';
                const type = isFreeBetInput ? 'freebet_placed' : 'bet_placed';
                
                const value = parseFloat(legEl.querySelector('.bet-value').value);
                const odd = parseFloat(legEl.querySelector('.bet-odd').value);
                
                // Ignorar pernas incompletas, mas isso deveria ser tratado pelo 'required'
                if (!accountId || value <= 0 || odd <= 0) {
                    showToast('Por favor, preencha todos os campos da aposta corretamente.', 'error');
                    success = false;
                    return;
                }

                totalBets.push({
                    conta_id: accountId,
                    tipo: type, 
                    valor: value, 
                    descricao: `${gameName} - ${isFreeBetInput ? 'Freebet' : 'Aposta'}`,
                    detalhes: {
                        operationId: operationId,
                        gameName: gameName,
                        category: 'esportes',
                        type: legsContainer.querySelectorAll('.leg-container').length > 1 ? 'multi' : 'simples',
                        status: 'ativa',
                        matchId: document.getElementById('operation-match-id').value || null,
                        odd: odd,
                    }
                });
            });
        }
        
        if (!success || totalBets.length === 0) {
            submitBtn.innerHTML = 'Registrar Operação';
            submitBtn.disabled = false;
            return;
        }

        // Enviar todas as apostas para o backend
        let allSuccess = true;
        for (const bet of totalBets) {
            try {
                 await apiRequest('/api/operacoes', 'POST', bet);
            } catch (error) {
                showToast(`Falha ao registrar aposta: ${error.message}`, 'error');
                allSuccess = false;
                break;
            }
        }

        if (allSuccess) {
            showToast('Operação registrada com sucesso!', 'success');
            modals.transaction.close();
            operationForm.reset();
            // Recriar a primeira perna (leg)
            legsContainer.innerHTML = ''; 
            addLegRow(); 
            // Fechar o modal
            document.getElementById('operation-modal').classList.remove('flex');
            initializeApp();
        } 
        
        submitBtn.innerHTML = 'Registrar Operação';
        submitBtn.disabled = false;
    });

    // 6. FORMULÁRIO DE RESOLUÇÃO
    resolveForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const opId = document.getElementById('resolve-operation-id').value;
        const status = document.getElementById('resolve-status').value;
        const ganhoTotal = parseFloat(document.getElementById('resolve-ganho-total').value) || 0;
        const submitBtn = e.submitter;
        submitBtn.innerHTML = '<div class="spinner mx-auto"></div>';
        submitBtn.disabled = true;

        if (status === 'ganha' && ganhoTotal <= 0) {
             showToast('O ganho total deve ser positivo para uma aposta ganha.', 'error');
             submitBtn.innerHTML = 'Resolver';
             submitBtn.disabled = false;
             return;
        }
        if (status === 'perdida' && ganhoTotal !== 0) {
             showToast('O ganho total deve ser zero para uma aposta perdida.', 'error');
             submitBtn.innerHTML = 'Resolver';
             submitBtn.disabled = false;
             return;
        }

        const data = {
            operationId: opId,
            status: status,
            ganho_total: ganhoTotal,
        };

        try {
            await apiRequest('/api/operacoes/resolver', 'POST', data);
            showToast(`Operação ${opId} resolvida com sucesso!`, 'success');
            modals.resolve.close();
            initializeApp();
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            submitBtn.innerHTML = 'Resolver';
            submitBtn.disabled = false;
        }
    });

    // Lógica para mostrar/esconder campo de ganho
    document.getElementById('resolve-status').addEventListener('change', (e) => {
        const ganhoContainer = document.getElementById('resolve-ganho-container');
        if (e.target.value === 'ganha') {
            ganhoContainer.classList.remove('hidden');
            document.getElementById('resolve-ganho-total').required = true;
        } else {
            ganhoContainer.classList.add('hidden');
            document.getElementById('resolve-ganho-total').required = false;
            document.getElementById('resolve-ganho-total').value = '0.00';
        }
    });


    // --- RENDERIZAÇÃO DE RELATÓRIO ---
    function renderReport(data) {
        const contasBody = document.getElementById('report-contas-body');
        contasBody.innerHTML = data.resumoContas.map(c => {
            const plClass = c.pl_total >= 0 ? 'text-green-600' : 'text-red-600';
            const plPercent = c.volume_apostado > 0 ? (c.pl_total / c.volume_apostado) * 100 : 0;
            return `
                <tr class="bg-white border-b hover:bg-gray-50">
                    <td class="px-6 py-3 font-medium text-gray-900">${c.nome}</td>
                    <td class="px-6 py-3">${formatCurrency(c.saldo)}</td>
                    <td class="px-6 py-3 text-blue-600">${formatCurrency(c.saldo_freebets)}</td>
                    <td class="px-6 py-3 font-bold ${plClass}">${formatCurrency(c.pl_total)}</td>
                    <td class="px-6 py-3 font-semibold ${plClass}">${formatPercent(plPercent)}</td>
                    <td class="px-6 py-3 text-sm">${formatCurrency(c.volume_apostado)}</td>
                    <td class="px-6 py-3 text-sm">${formatCurrency(c.meta)}</td>
                    <td class="px-6 py-3 text-sm">${formatCurrency(c.volume_clube)}</td>
                </tr>
            `;
        }).join('');

        const mensalBody = document.getElementById('report-mensal-body');
        mensalBody.innerHTML = data.resumoMensal.map(m => {
            const plClass = m.pl_mes >= 0 ? 'text-green-600' : 'text-red-600';
            const receita = m.pl_mes - m.despesas_mes - m.pagamentos_mes;
            const receitaClass = receita >= 0 ? 'text-green-600' : 'text-red-600';
            return `
                <tr class="bg-white border-b hover:bg-gray-50">
                    <td class="px-6 py-3 font-medium text-gray-900">${m.periodo}</td>
                    <td class="px-6 py-3 font-bold ${plClass}">${formatCurrency(m.pl_mes)}</td>
                    <td class="px-6 py-3 text-red-600">${formatCurrency(m.despesas_mes)}</td>
                    <td class="px-6 py-3 text-red-600">${formatCurrency(m.pagamentos_mes)}</td>
                    <td class="px-6 py-3 font-extrabold ${receitaClass}">${formatCurrency(receita)}</td>
                </tr>
            `;
        }).join('');
    }

    // --- LÓGICA DE TABS ---
    mainTabsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('tab-btn')) {
            const tabId = e.target.getAttribute('data-tab');
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            e.target.classList.add('active');
            document.getElementById(`tab-content-${tabId}`).classList.add('active');
        }
    });

    // Lógica para alternar entre formulário de Cassino e Esportes
    operationCategorySelect.addEventListener('change', () => {
        const isCasino = operationCategorySelect.value === 'cassino';
        document.getElementById('multi-bet-container').classList.toggle('hidden', isCasino);
        document.getElementById('cassino-container').classList.toggle('hidden', !isCasino);

        // Gerenciar campos obrigatórios
        document.querySelectorAll('#multi-bet-container [required]').forEach(el => el.required = !isCasino);
        document.querySelectorAll('#cassino-container [required]').forEach(el => el.required = isCasino);
        
        // Preenche o select de contas do Cassino
        if (isCasino) {
             populateAccountSelect(document.getElementById('cassino-account'));
        }
    });

    // --- INICIALIZAÇÃO ---
    async function initializeApp() {
        try {
            const data = await apiRequest('/api/dados-iniciais');
            allAccounts = data.contas;
            activeOperations = data.operacoesAtivas.map(op => {
                // Parse o JSON stringificado em detalhes
                try {
                    op.detalhes = JSON.parse(op.detalhes);
                } catch (e) {
                    console.error("Erro ao fazer parse de detalhes:", e);
                    op.detalhes = {};
                }
                return op;
            });
            transactionHistory = data.historico;

            renderTables();
            renderActiveOperations();
            renderTransactionHistory();
            updateFinancialSummary(data.resumoFinanceiro);

            // Re-renderiza pernas da aposta com as contas atualizadas
            if (legsContainer.children.length === 0) {
                addLegRow();
            } else {
                legsContainer.querySelectorAll('.bet-account').forEach(select => {
                    const sel = select.value;
                    select.innerHTML = getAccountOptionsHtml();
                    select.value = sel;
                });
                legsContainer.querySelectorAll('.leg-container').forEach(leg => updateLegSummary(leg));
            }

            // Garante que o container correto é exibido
            operationCategorySelect.dispatchEvent(new Event('change'));

        } catch (error) {
            // Este é o erro que estava sendo capturado
            showToast(`Erro fatal ao carregar: ${error.message}`, 'error');
        }
    }
    
    // Inicia o aplicativo
    initializeApp();
});
