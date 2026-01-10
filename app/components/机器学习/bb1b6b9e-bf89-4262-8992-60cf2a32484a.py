# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class TorchClassifierTrainer(BaseComponent):
    name = "PyTorch 分类模型训练"
    category = "机器学习"
    description = "使用 PyTorch 训练一个用于数据分类的神经网络模型，支持自定义结构与超参数配置。"
    requirements = "torch,scikit-learn"
    inputs = [
        PortDefinition(name="training_data", label="训练数据", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
        PortDefinition(name="labels", label="标签数据", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="classifier_model", label="训练好的模型", type=ArgumentType.TORCHMODEL),
        PortDefinition(name="training_loss", label="训练日志", type=ArgumentType.JSON),
        PortDefinition(name="accuracy", label="准确率", type=ArgumentType.JSON),
    ]
    properties = {
        "hidden_size": PropertyDefinition(
            type=PropertyType.INT,
            default=64,
            label="隐藏层大小",
        ),
        "learning_rate": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.0,
            label="学习率",
        ),
        "epochs": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="训练轮数",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=32,
            label="批量大小",
        ),
        "test_split": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.2,
            label="测试集比例",
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cuda",
            label="运行设备",
            choices=["cuda", "cpu"]
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader, TensorDataset
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder

        # 1. 读取输入数据
        try:
            df = inputs.training_data
            X = df.values
            y = inputs.labels.values
        except Exception as e:
            self.logger.error(f"数据读取失败: {str(e)}")
            raise

        # 2. 标签编码
        try:
            le = LabelEncoder()
            y_encoded = le.fit_transform(y)
        except Exception as e:
            self.logger.error(f"标签编码失败: {str(e)}")
            raise

        # 3. 划分训练/测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_encoded, test_size=params.test_split, random_state=42, stratify=y_encoded
        )

        # 4. 转为 Tensor
        X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
        y_train_tensor = torch.tensor(y_train, dtype=torch.long)
        X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
        y_test_tensor = torch.tensor(y_test, dtype=torch.long)

        # 5. 构建模型
        num_features = X_train.shape[1]
        num_classes = len(le.classes_)
        hidden_size = int(params.hidden_size)

        class SimpleClassifier(nn.Module):
            def __init__(self, input_size, hidden_size, num_classes):
                super(SimpleClassifier, self).__init__()
                self.fc1 = nn.Linear(input_size, hidden_size)
                self.fc2 = nn.Linear(hidden_size, hidden_size)
                self.fc3 = nn.Linear(hidden_size, num_classes)
                self.relu = nn.ReLU()
                self.dropout = nn.Dropout(0.3)

            def forward(self, x):
                x = self.relu(self.fc1(x))
                x = self.dropout(x)
                x = self.relu(self.fc2(x))
                x = self.dropout(x)
                x = self.fc3(x)
                return x

        model = SimpleClassifier(num_features, hidden_size, num_classes)
        device = torch.device(params.device)
        model.to(device)

        # 6. 定义损失与优化器
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=float(params.learning_rate))

        # 7. 训练循环
        train_losses = []
        accuracies = []
        epochs = int(params.epochs)
        batch_size = int(params.batch_size)

        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        for epoch in range(epochs):
            model.train()
            running_loss = 0.0
            correct = 0
            total = 0

            for inputs, targets in train_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                optimizer.step()

                running_loss += loss.item()
                _, predicted = outputs.max(1)
                total += targets.size(0)
                correct += predicted.eq(targets).sum().item()

            train_loss = running_loss / len(train_loader)
            acc = 100. * correct / total
            
            train_losses.append(train_loss)
            accuracies.append(acc)

            if (epoch + 1) % 50 == 0:
                self.emit_custom_message(
                method="stream.output",
                    params={
                        "training_loss": {"data": train_loss, "data_type": "list"},
                        "accuracy": {"data": acc, "data_type": "list"},
                    }
                )
                self.logger.info(f"Epoch [{epoch+1}/{epochs}], Loss: {train_loss:.4f}, Acc: {acc:.2f}%")

        # 8. 测试模型
        model.eval()
        with torch.no_grad():
            test_outputs = model(X_test_tensor.to(device))
            _, predicted = test_outputs.max(1)
            test_acc = 100. * predicted.eq(y_test_tensor.to(device)).sum().item() / len(y_test_tensor)

        # 9.准备预导出模型
        batch_dim = torch.export.Dim("batch")
        dynamic_shapes = {"x": {0: batch_dim}}
        exported_program = torch.export.export(
            model, args=(X_test_tensor.to(device),),
            dynamic_shapes=dynamic_shapes
        )
        # 10. 返回结果
        return {
            "classifier_model": exported_program,
            "training_loss": train_losses,
            "accuracy": accuracies
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = TorchClassifierTrainer()
    result = model.debug(
        params={
            "hidden_size": "64",
            "learning_rate": "0.001",
            "epochs": "50",
            "batch_size": "32",
            "test_split": "0.2",
            "labels": "target",
            "model_name": "test_model.pth"
        },
        inputs={
            "training_data": "sample_data.csv",
            "labels": "target"
        },
        global_vars={},
        node_id="torch_classifier_train",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)