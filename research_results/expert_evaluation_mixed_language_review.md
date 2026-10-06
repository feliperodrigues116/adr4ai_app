# Revisão dos 14 campos mistos

Revisão local pelo Codex. As porções originalmente em português foram restauradas literalmente e conferidas contra a fonte. Nenhuma avaliação arquitetural foi realizada.

Este arquivo é exclusivo para pesquisadores. Não apresentar aos avaliadores.

## 1. SYS03-US02 × 001 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will submeter o resultado da confirmação de titularidade feita pela IA a uma decisão determinística baseada em regras antes de solicitar ao sistema Comercial a alteração do status para PENDENTE DE EXECUÇÃO. Somente um resultado autorizado por essas regras poderá desencadear a mudança de status; um resultado não autorizado não a desencadeará.

**Versão candidata**

Vamos submeter o resultado da confirmação de titularidade feita pela IA a uma decisão determinística baseada em regras antes de solicitar ao sistema Comercial a alteração do status para PENDENTE DE EXECUÇÃO. Somente um resultado autorizado por essas regras poderá desencadear a mudança de status; um resultado não autorizado não a desencadeará.

## 2. SYS03-US02 × 003 — adr_context

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

After confirming that a document belongs to the customer, the AI system must change the service request status to PENDENTE DE EXECUÇÃO. That change must allow the Commercial system to notify the customer and continue scheduling the service. The architecture must define how the AI system requests the change while the Commercial system maintains the service request.

**Versão candidata**

Após confirmar que um documento pertence ao cliente, o sistema de IA deve alterar o status da solicitação de serviço para PENDENTE DE EXECUÇÃO. Essa alteração deve permitir que o sistema Comercial notifique o cliente e continue agendando o serviço. A arquitetura deve definir como o sistema de IA solicita a alteração enquanto o sistema Comercial mantém a solicitação de serviço.

## 3. SYS03-US02 × 003 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will have the AI system act as a client that requests a status change from the Commercial system. After confirming that the document belongs to the customer, the AI system will request that the Commercial system set the service request status to PENDENTE DE EXECUÇÃO. The Commercial system will perform the change, notify the customer, and continue scheduling the service.

**Versão candidata**

Faremos com que o sistema de IA atue como um cliente que solicita uma alteração de status ao sistema Comercial. Após confirmar que o documento pertence ao cliente, o sistema de IA solicitará que o sistema Comercial defina o status da solicitação de serviço como PENDENTE DE EXECUÇÃO. O sistema Comercial realizará a alteração, notificará o cliente e continuará agendando o serviço.

## 4. SYS03-US02 × 014 — adr_context

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

When the AI system confirms that a document belongs to the customer, it must change the service status in the Commercial system to PENDENTE DE EXECUÇÃO. That status change enables the Commercial system to notify the customer and proceed with scheduling. The architecture needs to distinguish the AI validation responsibility from these subsequent business activities.

**Versão candidata**

Quando o sistema de AI confirma que um documento pertence ao cliente, ele deve alterar o status do serviço no sistema Commercial para PENDENTE DE EXECUÇÃO. Essa mudança de status permite que o sistema Commercial notifique o cliente e prossiga com o agendamento. A arquitetura precisa distinguir a responsabilidade pela validação por AI dessas atividades de negócios subsequentes.

## 5. SYS03-US02 × 014 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will separate AI-based document validation from the Commercial system’s business workflow through a clear interface. After confirming that the document belongs to the customer, the AI system will communicate with the Commercial system to change the service status to PENDENTE DE EXECUÇÃO. The Commercial system will then handle customer notification and scheduling based on that status change.

**Versão candidata**

Vamos separar a validação de documentos baseada em AI do fluxo de trabalho de negócios do sistema Commercial por meio de uma interface clara. Após confirmar que o documento pertence ao cliente, o sistema de AI se comunicará com o sistema Commercial para alterar o status do serviço para PENDENTE DE EXECUÇÃO. O sistema Commercial então cuidará da notificação ao cliente e do agendamento com base nessa mudança de status.

## 6. SYS03-US02 × 044 — adr_context

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

When the AI system confirms that a document belongs to the customer, it must change the service request’s status in the company’s Commercial system to PENDENTE DE EXECUÇÃO. That change must lead the Commercial system to notify the customer and proceed with scheduling the service. The architecture needs to associate those actions with the request’s status.

**Versão candidata**

Quando o sistema de IA confirmar que um documento pertence ao cliente, ele deve alterar o status da solicitação de serviço no sistema Comercial da empresa para PENDENTE DE EXECUÇÃO. Essa alteração deve levar o sistema Comercial a notificar o cliente e a prosseguir com o agendamento do serviço. A arquitetura precisa associar essas ações ao status da solicitação.

## 7. SYS03-US02 × 044 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will make the Commercial system’s handling of a service request depend on its state. After confirming that the document belongs to the customer, the AI system will communicate with the Commercial system to change the request’s status to PENDENTE DE EXECUÇÃO. In that state, the Commercial system will notify the customer and proceed with scheduling the service.

**Versão candidata**

Faremos com que o tratamento de uma solicitação de serviço pelo sistema Comercial dependa de seu estado. Após confirmar que o documento pertence ao cliente, o sistema de IA se comunicará com o sistema Comercial para alterar o status da solicitação para PENDENTE DE EXECUÇÃO. Nesse estado, o sistema Comercial notificará o cliente e prosseguirá com o agendamento do serviço.

## 8. SYS03-US02 × 044 — adr_consequences

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

Customer notification and scheduling will follow the confirmed status change rather than occur independently of it. These actions will depend on the AI system successfully communicating the change and on the Commercial system maintaining the behavior associated with PENDENTE DE EXECUÇÃO.

**Versão candidata**

A notificação do cliente e o agendamento seguirão a alteração confirmada de status, em vez de ocorrerem independentemente dela. Essas ações dependerão de o sistema de IA comunicar a alteração com sucesso e de o sistema Comercial manter o comportamento associado a PENDENTE DE EXECUÇÃO.

## 9. SYS03-US02 × 050 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will hold the service request workflow until the AI system completes document validation. When validation confirms that the document belongs to the customer, the AI system will communicate with the Commercial system to change the status to PENDENTE DE EXECUÇÃO, allowing the Commercial system to notify the customer and proceed with scheduling.

**Versão candidata**

Manteremos o fluxo de trabalho da solicitação de serviço em espera até que o sistema de IA conclua a validação do documento. Quando a validação confirmar que o documento pertence ao cliente, o sistema de IA se comunicará com o sistema Comercial para mudar o status para PENDENTE DE EXECUÇÃO, permitindo que o sistema Comercial notifique o cliente e prossiga com o agendamento.

## 10. SYS03-US03 × 003 — adr_context

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

When the AI system confirms that a submitted document does not belong to the customer, it must mark the service as improcedente and record the reason in the company's Commercial system. The Commercial system must then notify the customer. The architecture needs to define how the AI system requests this update while leaving notification with the Commercial system.

**Versão candidata**

Quando o sistema de IA confirma que um documento enviado não pertence ao cliente, ele deve marcar o serviço como improcedente e registrar o motivo no sistema Comercial da empresa. O sistema Comercial deve então notificar o cliente. A arquitetura precisa definir como o sistema de IA solicita essa atualização, deixando a notificação a cargo do sistema Comercial.

## 11. SYS03-US03 × 003 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will make the AI system a client of the Commercial system, which will serve requests to update services. When the AI system confirms that a document does not belong to the customer, it will request that the Commercial system mark the service as improcedente and record the reason. The Commercial system will notify the customer when the service is closed.

**Versão candidata**

Tornaremos o sistema de IA um cliente do sistema Comercial, que atenderá às solicitações de atualização de serviços. Quando o sistema de IA confirmar que um documento não pertence ao cliente, ele solicitará que o sistema Comercial marque o serviço como improcedente e registre o motivo. O sistema Comercial notificará o cliente quando o serviço for encerrado.

## 12. SYS03-US03 × 050 — adr_context

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

The AI system processes documents submitted through integrated service-request applications. It must mark a service as improcedente in the company's Commercial system, with a reason, when it confirms that the document does not belong to the customer. The Commercial system then notifies the customer. The service update therefore depends on the outcome of the document check.

**Versão candidata**

O sistema de IA processa documentos enviados por meio de aplicativos integrados de solicitação de serviço. Ele deve marcar um serviço como improcedente no sistema Comercial da empresa, com um motivo, quando confirma que o documento não pertence ao cliente. O sistema Comercial então notifica o cliente. Portanto, a atualização do serviço depende do resultado da verificação do documento.

## 13. SYS03-US03 × 050 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will wait for the AI document check to finish before proceeding with the service update. If the check confirms that the document does not belong to the customer, we will mark the service as improcedente in the Commercial system and record the reason, allowing the Commercial system to notify the customer after the service is closed.

**Versão candidata**

Aguardaremos a conclusão da verificação do documento pela IA antes de prosseguir com a atualização do serviço. Se a verificação confirmar que o documento não pertence ao cliente, marcaremos o serviço como improcedente no sistema Comercial e registraremos o motivo, permitindo que o sistema Comercial notifique o cliente após o encerramento do serviço.

## 14. SYS04-US02 × 003 — adr_decision

Ação: `partially_translated_mixed`. Preservação literal das porções em português: PASSOU.

**Original**

We will establish the simulator as the server for these integration services, with the CLP, supervisory system, and external applications initiating connections as clients. O simulador disponibilizará as variáveis simuladas por OPC UA conforme a nomenclatura e os tipos de dados definidos para a ETA, receberá comandos permitidos e refletirá seus efeitos na simulação. As conexões com os clientes permitirão testar a perda e o restabelecimento da comunicação.

**Versão candidata**

Estabeleceremos o simulador como o servidor para esses serviços de integração, com o CLP, o sistema supervisório e as aplicações externas iniciando conexões como clientes. O simulador disponibilizará as variáveis simuladas por OPC UA conforme a nomenclatura e os tipos de dados definidos para a ETA, receberá comandos permitidos e refletirá seus efeitos na simulação. As conexões com os clientes permitirão testar a perda e o restabelecimento da comunicação.
