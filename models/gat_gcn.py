import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import Sequential, Linear, ReLU
from torch_geometric.nn import GCNConv, GATConv, GINConv, global_add_pool
from torch_geometric.nn import global_mean_pool as gap, global_max_pool as gmp

# GCN-CNN based model

class GAT_GCN(torch.nn.Module):
    def __init__(self, n_output=1, num_features_xd=78, num_features_xt=25,
                 n_filters=32, embed_dim=128, output_dim=128, dropout=0.2):

        super(GAT_GCN, self).__init__()

        self.n_output = n_output
        self.encoder_layer_1 = nn.TransformerEncoderLayer(d_model=num_features_xd, nhead=1, dropout=0.5)
        self.ugformer_layer_1 = nn.TransformerEncoder(self.encoder_layer_1, 1)
        self.conv1 = GATConv(num_features_xd, num_features_xd, heads=10)
        self.encoder_layer_2 = nn.TransformerEncoderLayer(d_model=num_features_xd*10, nhead=1, dropout=0.5)
        self.ugformer_layer_2 = nn.TransformerEncoder(self.encoder_layer_2, 1)
        self.conv2 = GCNConv(num_features_xd*10, num_features_xd*10)
        self.fc_g1 = torch.nn.Linear(num_features_xd * 10 * 2, 1024)
        self.fc_g2 = torch.nn.Linear(1024, output_dim)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

        # fingerprint features
        self.embedding_xf = nn.Embedding(num_features_xt + 1, embed_dim * 2)

        self.conv_xf_1 = nn.Conv1d(in_channels=167, out_channels=32, kernel_size=8)
        self.pool_xf_1 = nn.MaxPool1d(3)
        self.conv_xf_2 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=8)
        self.pool_xf_2 = nn.MaxPool1d(3)
        self.conv_xf_3 = nn.Conv1d(in_channels=64, out_channels=128, kernel_size=8)
        self.pool_xf_3 = nn.MaxPool1d(3)
        self.fc1_xf = nn.Linear(128*6, 1024)
        self.fc2_xf = nn.Linear(1024, output_dim)

        # cell line feature
        self.embedding_xt = nn.Embedding(num_features_xt + 1, embed_dim*2)

        self.conv_xt_1 = nn.LSTM(256, embed_dim, num_layers=2, batch_first=True, bidirectional=True)
        self.pool_xt_1 = nn.MaxPool1d(3)
        self.conv_xt_2 = nn.LSTM(85, embed_dim , num_layers=2, batch_first=True, bidirectional=True)
        self.pool_xt_2 = nn.MaxPool1d(3)
        self.conv_xt_3 = nn.LSTM(85, embed_dim, num_layers=2, batch_first=True, bidirectional=True)
        self.pool_xt_3 = nn.MaxPool1d(3)
        self.fc1_xt = nn.Linear(85* 735, 1024)
        self.fc2_xt = nn.Linear(1024, output_dim)

        #smiles
        self.embedding_xds = nn.Embedding(num_embeddings=65, embedding_dim=128*2)
        self.conv_xds_1 = nn.LSTM(256, embed_dim, num_layers=2, batch_first=True, bidirectional=True)
        self.conv_xds_2 = nn.LSTM(85, embed_dim, num_layers=2, batch_first=True, bidirectional=True)
        self.conv_xds_3 = nn.LSTM(85, embed_dim, num_layers=2, batch_first=True, bidirectional=True)
        self.fc1_xds = nn.Linear(85 * 100, 1024)
        self.fc2_xds = nn.Linear(1024, 128)


        # combined layers
        #self.fc1 = nn.Linear(2*output_dim, 1024)
        self.fc1 = nn.Linear(4*output_dim, 1024)
        self.fc2 = nn.Linear(1024, 128)
        self.out = nn.Linear(128, n_output)

        # activation and regularization
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.5)

    def forward(self, data):
        x, edge_index, batch = data.x, data.edge_index, data.batch
        x = torch.unsqueeze(x, 1)
        x = self.ugformer_layer_1(x)
        x = torch.squeeze(x, 1)
        x = self.conv1(x, edge_index)
        x = self.relu(x)
        x = torch.unsqueeze(x, 1)
        x = self.ugformer_layer_2(x)
        x = torch.squeeze(x, 1)
        x = self.conv2(x, edge_index)
        x = self.relu(x)
        # apply global max pooling (gmp) and global mean pooling (gap)
        x = torch.cat([gmp(x, batch), gap(x, batch)], dim=1)
        x = self.relu(self.fc_g1(x))
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.fc_g2(x)
        x = F.dropout(x, p=0.2, training=self.training)

        # protein input feed-forward:
        target = data.target
        #target = target[:,None,:]
        target = target.long()
        target = self.embedding_xt(target)
        #print("=======target.shape=========")
        #print(target.shape)

        # 1d conv layers
        conv_xt = self.conv_xt_1(target)
        conv_xt = F.relu(conv_xt[0])
        conv_xt = self.pool_xt_1(conv_xt)
        # print("==========conv_xt.shape===========")
        # print(conv_xt.shape)
        conv_xt = self.conv_xt_2(conv_xt)
        conv_xt = conv_xt[0]
        conv_xt = F.relu(conv_xt)
        conv_xt = self.pool_xt_2(conv_xt)
        conv_xt = self.conv_xt_3(conv_xt)
        conv_xt = conv_xt[0]
        conv_xt = F.relu(conv_xt)
        conv_xt = self.pool_xt_3(conv_xt)
        # print("==========conv_xt.shape===========")
        # print(conv_xt.shape)
        # flatten
        xt = conv_xt.view(-1, conv_xt.shape[1] * conv_xt.shape[2])
        #print("=======xt11111111.shape=========")
        #print(xt.shape)
        xt = torch.relu(self.fc1_xt(xt))
        xt = F.dropout(xt, p=0.2, training=self.training)
        #print("=======xt222.shape=========")
        #print(xt.shape)
        xt = self.fc2_xt(xt)
        xt = F.dropout(xt, p=0.2, training=self.training)

        fingerprints = data.fingerprints
        # print("======drug.shape===========")
        # print(drug.shape)
        fingerprints = fingerprints.long()
        embedded_xf = self.embedding_xf(fingerprints)
        conv_xf = self.conv_xf_1(embedded_xf)
        conv_xf = torch.relu(conv_xf)
        conv_xf = self.pool_xf_1(conv_xf)

        conv_xf = self.conv_xf_2(conv_xf)
        conv_xf = torch.relu(conv_xf)
        conv_xf = self.pool_xf_2(conv_xf)

        conv_xf = self.conv_xf_3(conv_xf)
        conv_xf = torch.relu(conv_xf)
        conv_xf = self.pool_xf_3(conv_xf)
        conv_xf = conv_xf.view(-1, conv_xf.shape[1] * conv_xf.shape[2])

        fingerprints = torch.relu(self.fc1_xf(conv_xf))
        fingerprints = F.dropout(fingerprints, p=0.2, training=self.training)
        fingerprints = self.fc2_xf(fingerprints)
        fingerprints = F.dropout(fingerprints, p=0.2, training=self.training)


        drug = data.drug
        #print("======drug.shape===========")
        #print(drug.shape)
        drug = drug.long()
        embedded_xds = self.embedding_xds(drug)
        conv_xds = self.conv_xds_1(embedded_xds)
        conv_xds = torch.relu(conv_xds[0])
        conv_xds = self.pool_xt_1(conv_xds)

        conv_xds = self.conv_xds_2(conv_xds)
        conv_xds = torch.relu(conv_xds[0])
        conv_xds = self.pool_xt_2(conv_xds)

        conv_xds = self.conv_xds_3(conv_xds)
        conv_xds = torch.relu(conv_xds[0])
        conv_xds = self.pool_xt_3(conv_xds)
        conv_xds = conv_xds.view(-1, conv_xds.shape[1] * conv_xds.shape[2])

        drug = torch.relu(self.fc1_xds(conv_xds))
        drug = F.dropout(drug, p=0.2, training=self.training)
        drug = self.fc2_xds(drug)
        drug = F.dropout(drug, p=0.2, training=self.training)
        
        # concat
        #xc = torch.cat((x, xt), 1)
        xc = torch.cat((x, drug, fingerprints,xt), 1)

        # add some dense layers
        xc = self.fc1(xc)
        xc = self.relu(xc)
        xc = self.dropout(xc)
        xc = self.fc2(xc)
        xc = self.relu(xc)
        xc = self.dropout(xc)
        out = self.out(xc)
        out = nn.Sigmoid()(out)
        return out, x
