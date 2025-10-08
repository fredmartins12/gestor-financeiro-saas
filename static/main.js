document.addEventListener('DOMContentLoaded', () => {
    // --- ESTADO GLOBAL DA APLICAÇÃO ---
    let allAccounts = [];
    let activeOperations = [];
    let transactionHistory = [];

    // --- SELETORES DE ELEMENTOS DO DOM ---
    const modals = { account: setupModal(document.getElementById('account-modal')), transaction: setupModal(document.getElementById('transaction-modal')), expense: setupModal(document.getElementById('expense-modal')), transfer: setupModal(document.getElementById('transfer-modal')), report: setupModal(document.getElementById('report-modal')), }; const addAccountBtn = document.getElementById('add-account-btn'); const addTransactionBtn = document.getElementById('add-transaction-btn'); const addExpenseBtn = document.getElementById('add-expense-btn'); const transferBtn = document.getElementById('transfer-btn'); const reportBtn = document.getElementById('report-btn'); const backupBtn = document.getElementById('backup-btn'); const accountForm = document.getElementById('account-form'); const transactionForm = document.getElementById('transaction-form'); const expenseForm = document.getElementById('expense-form'); const transferForm = document.getElementById('transfer-form'); const operationForm = document.getElementById('operation-form'); const operationCategorySelect = document.getElementById('operation-category'); const legsContainer = document.getElementById('legs-container'); const addLegBtn = document.getElementById('add-leg-btn'); const activeOperationsContainer = document.getElementById('active-operations-container'); const mainTabsContainer = document.getElementById('main-tabs-container'); const mainContainer = document.querySelector('.max-w-screen-xl');

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
            initializeApp();
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
            initializeApp();
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
        const options = { method, headers: { 'Content-Type': 'application/json' } };
        if (body) options.body = JSON.stringify(body);
        const response = await fetch(endpoint, options);
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            return response.json();
        } else {
            return { message: 'Success' };
        }
    }

    // --- FUNÇÕES DE UI E UTILITÁRIOS ---
    const formatCurrency = (value) => `R$ ${(typeof value === 'number' ? value : 0).toFixed(2).replace('.', ',')}`; const floorToTwoDecimals = (num) => { const numAsFloat = parseFloat(num); if (isNaN(numAsFloat)) return 0; return Math.floor(numAsFloat * 100) / 100; }; function showToast(message, type = 'success') { const toastContainer = document.getElementById('toast-container'); const toast = document.createElement('div'); toast.className = `toast ${type}`; toast.textContent = message; toastContainer.appendChild(toast); setTimeout(() => toast.remove(), 5000); } function setupModal(modalElement) { const controller = { element: modalElement, open: () => modalElement.classList.add('flex'), close: () => modalElement.classList.remove('flex'), }; modalElement.addEventListener('click', (e) => { if (e.target === modalElement || e.target.closest('.cancel-modal-btn')) controller.close(); }); return controller; }

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
                    if (acc.saldo < 150 && provider !== 'pessoal') {
                        statusHtml = `<span class="status-tag tag-deposit">💰 Depósito</span>`;
                    }
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

                    let paymentHtml = 'N/A';
                    if (acc.dia_pagamento && provider !== 'pessoal') {
                        const today = new Date();
                        const currentYear = today.getFullYear();
                        const currentMonth = today.getMonth(); // 0-11
                        const currentPeriod = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
                        const dueDateThisMonth = new Date(currentYear, currentMonth, acc.dia_pagamento);
                        
                        if (acc.ultimo_periodo_pago === currentPeriod) {
                            const nextDueDate = new Date(currentYear, currentMonth + 1, acc.dia_pagamento);
                            const nextDateStr = `${String(nextDueDate.getDate()).padStart(2, '0')}/${String(nextDueDate.getMonth() + 1).padStart(2, '0')}`;
                            paymentHtml = `<span class="tag-paid">Pago ✔ (Próximo: ${nextDateStr})</span>`;
                        } else {
                            const diffTime = dueDateThisMonth.getTime() - today.getTime();
                            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                            const dueDateStr = `${String(dueDateThisMonth.getDate()).padStart(2, '0')}/${String(dueDateThisMonth.getMonth() + 1).padStart(2, '0')}`;
                            
                            if (diffDays < 0) {
                                paymentHtml = `<span class="tag-overdue">${dueDateStr} (Vencido há ${Math.abs(diffDays)} dias)</span>`;
                            } else {
                                paymentHtml = `<span class="tag-due">${dueDateStr} (Vence em ${diffDays} dias)</span>`;
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
                                <span class="action-btn edit-btn">Editar</span>
                                <span class="action-btn delete-btn">Excluir</span>
                            </td>
                        </tr>
                    `;
                }).join('');
        });
    }
    
    function renderActiveOperations() { if (activeOperations.length === 0) { activeOperationsContainer.innerHTML = `<p class="text-gray-500 bg-white shadow-md rounded-lg p-6">Nenhuma operação ativa no momento.</p>`; return; } const opsById = activeOperations.reduce((acc, bet) => { const details = JSON.parse(bet.detalhes); const opId = details.operationId; if (!acc[opId]) { acc[opId] = { gameName: bet.descricao.split(' - ')[0], bets: [] }; } acc[opId].bets.push({ ...bet, detalhes: details }); return acc; }, {}); activeOperationsContainer.innerHTML = Object.entries(opsById).map(([opId, op]) => { const marketsHtml = op.bets.map(bet => ` <div class="border-t py-3"> <label class="flex items-center space-x-3 cursor-pointer"> <input type="radio" name="winner_${opId}" value="${bet.detalhes.result}" class="market-winner-radio h-5 w-5 rounded-full border-gray-300 text-indigo-600"> <span class="font-semibold text-gray-800">${bet.detalhes.result} (@${parseFloat(bet.detalhes.odd).toFixed(5)})</span> </label> <p class="pl-8 text-sm text-gray-600">${bet.nome_conta} - ${formatCurrency(bet.detalhes.stake)}</p> </div>`).join(''); const lostHtml = ` <div class="border-t py-3"> <label class="flex items-center space-x-3 cursor-pointer"> <input type="checkbox" class="lost-operation-checkbox h-5 w-5 rounded border-gray-300 text-red-600"> <span class="font-semibold text-red-700">Nenhum Vencedor (Operação Perdida)</span> </label> </div>`; return `<div class="bg-white shadow-md rounded-lg operation-card" data-op-id="${opId}"> <div class="operation-header flex justify-between items-center p-4 cursor-pointer toggle-details-btn"> <div><h3 class="text-lg font-bold text-gray-900">${op.gameName}</h3><p class="text-xs text-gray-500 capitalize font-semibold">${op.bets[0].detalhes.category}</p></div> <span class="toggle-icon text-gray-500 font-bold text-xl">▼</span> </div> <div class="operation-body border-t px-4"><div class="py-4">${marketsHtml}${lostHtml}<div class="mt-4 border-t pt-4 text-right"><button class="resolve-operation-btn bg-green-600 text-white font-bold py-2 px-6 rounded-md hover:bg-green-700">Resolver Operação</button></div></div></div> </div>`; }).join(''); }
    function renderTransactionHistory() { const tbody = document.getElementById('transactions-history-body'); tbody.innerHTML = transactionHistory.length === 0 ? `<tr><td colspan="6" class="text-center p-4">Nenhum histórico encontrado.</td></tr>` : transactionHistory.map(trans => ` <tr class="border-t" data-transaction-id="${trans.id}"> <td class="px-6 py-4">${new Date(trans.data_criacao).toLocaleDateString('pt-BR')}</td> <td class="px-6 py-4">${trans.nome_conta}</td> <td class="px-6 py-4">${trans.descricao}</td> <td class="px-6 py-4 text-xs uppercase font-semibold">${trans.tipo.replace(/_/g, ' ')}</td> <td class="px-6 py-4 font-bold ${trans.valor >= 0 ? 'text-green-600' : 'text-red-600'}">${formatCurrency(trans.valor)}</td> <td class="px-6 py-4 text-center"> <button title="Excluir/Reverter Transação" class="delete-transaction-btn text-red-500 hover:text-red-700">🗑️</button> </td> </tr>`).join(''); }
    function updateFinancialSummary(summary) { const { monthly_credits, monthly_debits, monthly_net } = summary; const personalBalance = allAccounts.filter(a => a.casa_de_aposta === 'pessoal').reduce((sum, acc) => sum + acc.saldo, 0); const bettingHousesBalance = allAccounts.filter(a => a.casa_de_aposta !== 'pessoal').reduce((sum, acc) => sum + acc.saldo, 0); const totalFreebets = allAccounts.reduce((sum, acc) => sum + acc.saldo_freebets, 0); document.getElementById('personal-balance').textContent = formatCurrency(personalBalance); document.getElementById('betting-houses-balance').textContent = formatCurrency(bettingHousesBalance); document.getElementById('total-freebets-balance').textContent = formatCurrency(totalFreebets); document.getElementById('total-balance').textContent = formatCurrency(personalBalance + bettingHousesBalance); document.getElementById('monthly-credits').textContent = formatCurrency(monthly_credits); document.getElementById('monthly-debits').textContent = formatCurrency(Math.abs(monthly_debits)); const netElement = document.getElementById('monthly-net'); netElement.textContent = formatCurrency(monthly_net); netElement.classList.remove('text-green-600', 'text-red-600', 'text-gray-800'); if (monthly_net > 0) netElement.classList.add('text-green-600'); else if (monthly_net < 0) netElement.classList.add('text-red-600'); else netElement.classList.add('text-gray-800'); }
    function renderReport(data) { const { summary, accountAnalysis } = data; const finalBalance = summary.netProfit + summary.totalExpenses + summary.totalPayments; const reportContent = document.getElementById('report-content'); const summaryHtml = ` <div class="mb-8"> <h4 class="text-lg font-bold text-gray-800 mb-3">Resumo Geral do Mês</h4> <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-center"> <div class="bg-white shadow rounded-lg p-4"> <h5 class="text-sm font-semibold text-gray-500">LUCRO LÍQUIDO (APOSTAS)</h5> <p class="text-2xl font-bold ${summary.netProfit >= 0 ? 'text-green-600' : 'text-red-600'}">${formatCurrency(summary.netProfit)}</p> </div> <div class="bg-white shadow rounded-lg p-4"> <h5 class="text-sm font-semibold text-gray-500">TOTAL EM PAGAMENTOS</h5> <p class="text-2xl font-bold text-red-600">${formatCurrency(Math.abs(summary.totalPayments))}</p> </div> <div class="bg-white shadow rounded-lg p-4"> <h5 class="text-sm font-semibold text-gray-500">TOTAL EM GASTOS</h5> <p class="text-2xl font-bold text-rose-600">${formatCurrency(Math.abs(summary.totalExpenses))}</p> </div> <div class="bg-white shadow rounded-lg p-4"> <h5 class="text-sm font-semibold text-gray-500">BALANÇO FINAL</h5> <p class="text-2xl font-bold ${finalBalance >= 0 ? 'text-green-600' : 'text-red-600'}">${formatCurrency(finalBalance)}</p> </div> </div> </div>`; const accountTableHtml = accountAnalysis.length > 0 ? ` <div class="mb-8"> <h4 class="text-lg font-bold text-gray-800 mb-3">Análise por Conta</h4> <div class="bg-white shadow rounded-lg overflow-hidden"> <table class="w-full text-sm"> <thead class="text-xs text-gray-700 uppercase bg-gray-100"> <tr> <th class="px-6 py-3 text-left">CONTA</th> <th class="px-6 py-3 text-center">Nº DE APOSTAS</th> <th class="px-6 py-3 text-right">TOTAL APOSTADO</th> <th class="px-6 py-3 text-right">LUCRO / PREJUÍZO</th> </tr> </thead> <tbody> ${accountAnalysis.sort((a, b) => b.profit - a.profit).map(acc => ` <tr> <td class="px-6 py-4 text-left font-medium">${acc.name}</td> <td class="px-6 py-4 text-center">${acc.betCount}</td> <td class="px-6 py-4 text-right">${formatCurrency(acc.wagered)}</td> <td class="px-6 py-4 text-right font-bold ${acc.profit >= 0 ? 'text-green-600' : 'text-red-600'}"> ${formatCurrency(acc.profit)} </td> </tr> `).join('')} </tbody> </table> </div> </div>` : ''; reportContent.innerHTML = summaryHtml + accountTableHtml; }
    
    // --- LÓGICA DE EVENTOS ---
    addAccountBtn.addEventListener('click', () => { accountForm.reset(); document.getElementById('modal-title').textContent = 'Cadastrar Nova Conta'; modals.account.open(); });
    addTransactionBtn.addEventListener('click', () => { transactionForm.reset(); document.getElementById('transaction-account').innerHTML = getAccountOptionsHtml(); modals.transaction.open(); });
    addExpenseBtn.addEventListener('click', () => { expenseForm.reset(); document.getElementById('expense-account').innerHTML = allAccounts.filter(a => a.casa_de_aposta === 'pessoal').map(acc => `<option value="${acc.id}">${acc.nome}</option>`).join(''); modals.expense.open(); });
    transferBtn.addEventListener('click', () => { transferForm.reset(); const opts = getAccountOptionsHtml(); document.getElementById('transfer-from').innerHTML = opts; document.getElementById('transfer-to').innerHTML = opts; modals.transfer.open(); });
    backupBtn.addEventListener('click', () => { window.location.href = '/api/backup'; });
    reportBtn.addEventListener('click', () => { const monthSelect = document.getElementById('report-month'); const yearSelect = document.getElementById('report-year'); const now = new Date(); if (yearSelect.options.length === 0) { for (let y = now.getFullYear(); y >= 2023; y--) yearSelect.add(new Option(y, y)); const months = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]; months.forEach((m, i) => monthSelect.add(new Option(m, i + 1))); } yearSelect.value = now.getFullYear(); monthSelect.value = now.getMonth() + 1; const generate = async () => { document.getElementById('report-content').innerHTML = '<div class="spinner mx-auto"></div>'; try { const data = await apiRequest(`/api/relatorio?year=${yearSelect.value}&month=${monthSelect.value}`); renderReport(data); } catch (error) { showToast(`Erro ao gerar relatório: ${error.message}`, 'error'); } }; monthSelect.onchange = generate; yearSelect.onchange = generate; generate(); modals.report.open(); });
    accountForm.addEventListener('submit', async (e) => { e.preventDefault(); try { const id = e.target.elements['account-id'].value; const data = { nome: e.target.elements['account-name'].value, casaDeAposta: e.target.elements['account-provider'].value, saldo: parseFloat(e.target.elements['account-balance'].value || 0), saldoFreebets: parseFloat(e.target.elements['account-freebet-balance'].value || 0), diaPagamento: parseInt(e.target.elements['account-payment-day'].value) || null, valorPagamento: parseFloat(e.target.elements['account-payment-value'].value) || null, meta: parseFloat(e.target.elements['account-goal'].value || 100), volumeClube: parseFloat(e.target.elements['account-club-volume'].value || 0), observacoes: e.target.elements['account-obs'].value, dataUltimoCodigo: e.target.elements['account-last-code-date'].value || null, ultimoPeriodoPago: id ? allAccounts.find(a => a.id == id)?.ultimo_periodo_pago : null }; if (id) { await apiRequest(`/api/contas/${id}`, 'PUT', data); showToast('Conta atualizada!'); } else { await apiRequest('/api/contas', 'POST', data); showToast('Conta criada!'); } modals.account.close(); initializeApp(); } catch (error) { showToast(`Erro ao salvar conta: ${error.message}`, 'error'); } });
    transactionForm.addEventListener('submit', async (e) => { e.preventDefault(); try { await apiRequest('/api/transacoes/generico', 'POST', { accountId: e.target.elements['transaction-account'].value, type: e.target.elements['transaction-type'].value, amount: e.target.elements['transaction-amount'].value, description: e.target.elements['transaction-description'].value }); showToast('Lançamento registrado!'); modals.transaction.close(); initializeApp(); } catch(error) { showToast(`Erro: ${error.message}`, 'error'); } });
    expenseForm.addEventListener('submit', async (e) => { e.preventDefault(); try { await apiRequest('/api/transacoes/generico', 'POST', { accountId: e.target.elements['expense-account'].value, type: 'expense', amount: e.target.elements['expense-amount'].value, description: e.target.elements['expense-description'].value }); showToast('Gasto registrado!'); modals.expense.close(); initializeApp(); } catch(error) { showToast(`Erro: ${error.message}`, 'error'); } });
    transferForm.addEventListener('submit', async (e) => { e.preventDefault(); const fromId = e.target.elements['transfer-from'].value, toId = e.target.elements['transfer-to'].value; if(fromId === toId) return showToast('As contas não podem ser iguais.', 'error'); const toName = allAccounts.find(a => a.id == toId)?.nome || 'Outra Conta'; try { await apiRequest('/api/transferencia', 'POST', { fromId, toId, amount: e.target.elements['transfer-amount'].value, description: e.target.elements['transfer-description'].value || toName }); showToast('Transferência realizada!'); modals.transfer.close(); initializeApp(); } catch(error) { showToast(`Erro: ${error.message}`, 'error'); } });
    
    operationForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            const operationData = {
                gameName: e.target.elements['operation-game-name'].value,
                category: e.target.elements['operation-category'].value,
                legs: Array.from(legsContainer.querySelectorAll('.leg-container')).map(leg => ({
                    result: leg.querySelector('.leg-result').value,
                    odd: leg.querySelector('.leg-odd').value,
                    accounts: Array.from(leg.querySelectorAll('.account-stake-row')).map(row => ({
                        accountId: row.querySelector('.bet-account').value,
                        stake: floorToTwoDecimals(row.querySelector('.bet-stake').value),
                        isFreebet: row.querySelector('.bet-is-freebet-checkbox')?.checked ?? false
                    }))
                }))
            };
            await apiRequest('/api/operacoes', 'POST', operationData);
            showToast('Operação registrada!');
            operationForm.reset();
            legsContainer.innerHTML = '';
            addLegRow();
            initializeApp();
        } catch (error) {
            showToast(`Erro: ${error.message}`, 'error');
        }
    });

    mainContainer.addEventListener('click', async (e) => { const target = e.target; if (target.classList.contains('pay-btn')) { const accountId = target.dataset.accountId; const accountName = target.dataset.accountName; if (confirm(`Confirmar o pagamento para a conta "${accountName}" para o período atual?`)) { try { await apiRequest(`/api/contas/${accountId}/pagar`, 'POST'); showToast('Pagamento registrado com sucesso!'); initializeApp(); } catch (err) { showToast(`Erro ao registrar pagamento: ${err.message}`, 'error'); } } } const accountRow = target.closest('tr[data-account-id]'); const transactionRow = target.closest('tr[data-transaction-id]'); if (accountRow) { const accountId = accountRow.dataset.accountId; const account = allAccounts.find(a => a.id == accountId); if (target.classList.contains('edit-btn')) { document.getElementById('modal-title').textContent = 'Editar Conta'; document.getElementById('account-id').value = account.id; document.getElementById('account-name').value = account.nome; document.getElementById('account-provider').value = account.casa_de_aposta; document.getElementById('account-balance').value = account.saldo; document.getElementById('account-freebet-balance').value = account.saldo_freebets; document.getElementById('account-payment-day').value = account.dia_pagamento; document.getElementById('account-payment-value').value = account.valor_pagamento; document.getElementById('account-goal').value = account.meta; document.getElementById('account-club-volume').value = account.volume_clube; document.getElementById('account-obs').value = account.observacoes; document.getElementById('account-last-code-date').value = account.data_ultimo_codigo; modals.account.open(); } if (target.classList.contains('delete-btn')) { if (confirm(`Desativar a conta "${account.nome}"?`)) { try { await apiRequest(`/api/contas/${accountId}`, 'DELETE'); showToast('Conta desativada!'); initializeApp(); } catch (err) { showToast(`Erro: ${err.message}`, 'error'); } } } } if (transactionRow && target.classList.contains('delete-transaction-btn')) { if (confirm('Excluir e reverter esta transação? A ação não pode ser desfeita.')) { try { await apiRequest(`/api/transacoes/${transactionRow.dataset.transactionId}`, 'DELETE'); showToast('Transação revertida!'); initializeApp(); } catch (err) { showToast(`Erro ao reverter: ${err.message}`, 'error'); } } } if (target.closest('.toggle-details-btn')) { target.closest('.operation-card').classList.toggle('is-expanded'); } if (target.classList.contains('resolve-operation-btn')) { const card = target.closest('.operation-card'); const operationId = card.dataset.opId; const winnerRadio = card.querySelector('.market-winner-radio:checked'); const isLost = card.querySelector('.lost-operation-checkbox:checked'); if (winnerRadio && isLost) { return showToast('Não é possível marcar um vencedor E a operação como perdida.', 'error'); } if (!winnerRadio && !isLost) { return showToast('Selecione um resultado vencedor OU marque a operação como perdida.', 'error'); } const winningMarket = isLost ? null : winnerRadio.value; try { await apiRequest('/api/operacoes/resolver', 'POST', { operationId, winningMarket }); showToast('Operação resolvida com sucesso!'); initializeApp(); } catch (err) { showToast(`Erro ao resolver: ${err.message}`, 'error'); } } });

    function updateLegSummary(legContainer) {
        if (!legContainer) return;
        let totalStake = 0;
        let totalPotentialReturn = 0;
        const odd = parseFloat(legContainer.querySelector('.leg-odd').value) || 0;
        const accountRows = legContainer.querySelectorAll('.account-stake-row');
        accountRows.forEach(row => {
            const stake = parseFloat(row.querySelector('.bet-stake').value) || 0;
            const isFreebet = row.querySelector('.bet-is-freebet-checkbox').checked;
            totalStake += stake;
            if (isFreebet) {
                totalPotentialReturn += stake * (odd > 1 ? odd - 1 : 0);
            } else {
                totalPotentialReturn += stake * odd;
            }
        });
        const summaryEl = legContainer.querySelector('.leg-summary');
        if (totalStake > 0) {
            summaryEl.innerHTML = `Total Apostado: <span class="text-red-600">${formatCurrency(totalStake)}</span> | Retorno Possível: <span class="text-green-600">${formatCurrency(totalPotentialReturn)}</span>`;
        } else {
            summaryEl.innerHTML = '';
        }
    }

    function getAccountOptionsHtml() { return allAccounts.map(acc => `<option value="${acc.id}">${acc.nome} (${formatCurrency(acc.saldo)})</option>`).join(''); }
    function addAccountStakeRow() { const row = document.createElement('div'); row.className = 'flex items-center gap-2 mt-2 account-stake-row'; row.innerHTML = `<select class="bet-account block w-full rounded-md border-gray-300 text-sm">${getAccountOptionsHtml()}</select><input type="number" step="0.01" class="bet-stake block w-40 rounded-md border-gray-300 text-sm" placeholder="Valor (R$)" required><label class="flex items-center text-xs whitespace-nowrap"><input type="checkbox" class="bet-is-freebet-checkbox h-4 w-4 mr-1"> Usar FB?</label><button type="button" class="remove-account-stake-btn text-red-500 font-bold ml-auto">X</button>`; return row; }

    function addLegRow() {
        const legWrapper = document.createElement('div');
        legWrapper.className = 'p-4 border rounded-lg bg-gray-50 leg-container';
        legWrapper.innerHTML = `
            <div class="relative grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs">Resultado / Mercado</label>
                    <input type="text" class="leg-result mt-1 block w-full rounded-md border-gray-300" required>
                </div>
                <div class="flex items-end gap-3">
                    <div class="flex-grow">
                        <label class="block text-xs">Odd</label>
                        <input type="number" step="0.0001" class="leg-odd mt-1 block w-full rounded-md border-gray-300" required>
                    </div>
                    <label class="flex items-center pb-1 whitespace-nowrap text-sm">
                        <input type="checkbox" class="same-value-checkbox h-4 w-4 mr-1"> Mesmo Valor?
                    </label>
                </div>
                <button type="button" class="remove-leg-btn absolute -top-2 -right-2 bg-red-500 text-white rounded-full h-6 w-6 flex items-center justify-center font-bold text-sm">✕</button>
            </div>
            <div class="mt-4 border-t pt-4">
                <div class="accounts-stakes-container space-y-2"></div>
                <button type="button" class="add-account-stake-btn mt-2 text-sm text-blue-600 hover:underline">+ Adicionar Conta</button>
                <div class="leg-summary mt-3 text-sm font-bold text-right"></div>
            </div>`;
        legWrapper.querySelector('.accounts-stakes-container').appendChild(addAccountStakeRow());
        legsContainer.appendChild(legWrapper);
        updateLegSummary(legWrapper);
    }

    addLegBtn.addEventListener('click', addLegRow);

    legsContainer.addEventListener('input', e => {
        const legContainer = e.target.closest('.leg-container');
        if (!legContainer) return;
        if (e.target.classList.contains('bet-stake')) {
            const isSameValue = legContainer.querySelector('.same-value-checkbox').checked;
            if (isSameValue) {
                const sourceValue = e.target.value;
                legContainer.querySelectorAll('.bet-stake').forEach(input => {
                    if (input !== e.target) { input.value = sourceValue; }
                });
            }
        }
        updateLegSummary(legContainer);
    });

    legsContainer.addEventListener('change', e => {
        const legContainer = e.target.closest('.leg-container');
        if (!legContainer) return;
        if (e.target.classList.contains('bet-is-freebet-checkbox') || e.target.classList.contains('same-value-checkbox')) {
             if (e.target.classList.contains('same-value-checkbox') && e.target.checked) {
                 const firstStake = legContainer.querySelector('.bet-stake')?.value || '';
                 legContainer.querySelectorAll('.bet-stake').forEach(input => input.value = firstStake);
            }
            updateLegSummary(legContainer);
        }
    });

    legsContainer.addEventListener('click', e => {
        const legContainer = e.target.closest('.leg-container');
        if (!legContainer) return;
        if (e.target.classList.contains('remove-leg-btn')) { legContainer.remove(); } 
        else if (e.target.classList.contains('add-account-stake-btn')) {
            const container = legContainer.querySelector('.accounts-stakes-container');
            const newRow = addAccountStakeRow();
            const isSameValue = legContainer.querySelector('.same-value-checkbox').checked;
            if (isSameValue) {
                const firstStakeValue = legContainer.querySelector('.bet-stake')?.value || '';
                newRow.querySelector('.bet-stake').value = firstStakeValue;
            }
            container.appendChild(newRow);
            updateLegSummary(legContainer);
        } 
        else if (e.target.classList.contains('remove-account-stake-btn')) {
            e.target.closest('.account-stake-row').remove();
            updateLegSummary(legContainer);
        }
    });

    mainTabsContainer.addEventListener('click', (e) => { if (e.target.classList.contains('tab-btn')) { const tabId = e.target.dataset.tab; document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active')); document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active')); e.target.classList.add('active'); document.getElementById(`tab-content-${tabId}`).classList.add('active'); } });
    operationCategorySelect.addEventListener('change', () => { const isCasino = operationCategorySelect.value === 'cassino'; document.getElementById('multi-bet-container').classList.toggle('hidden', isCasino); document.getElementById('cassino-container').classList.toggle('hidden', !isCasino); document.querySelectorAll('#multi-bet-container [required]').forEach(el => el.required = !isCasino); document.querySelectorAll('#cassino-container [required]').forEach(el => el.required = isCasino); });

    async function initializeApp() { try { const data = await apiRequest('/api/dados-iniciais'); allAccounts = data.contas; activeOperations = data.operacoesAtivas; transactionHistory = data.historico; renderTables(); renderActiveOperations(); renderTransactionHistory(); updateFinancialSummary(data.resumoFinanceiro); if (legsContainer.children.length === 0) { addLegRow(); } else { legsContainer.querySelectorAll('.bet-account').forEach(select => { const sel = select.value; select.innerHTML = getAccountOptionsHtml(); select.value = sel; }); legsContainer.querySelectorAll('.leg-container').forEach(leg => updateLegSummary(leg)); } operationCategorySelect.dispatchEvent(new Event('change')); } catch (error) { showToast(`Erro fatal ao carregar: ${error.message}`, 'error'); } }
    
    initializeApp();
});
